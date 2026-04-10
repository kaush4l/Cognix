from typing import List, Any
import ast
import concurrent.futures
import inspect
import logging
import re
import time
from pydantic import BaseModel, Field

from core.responses import BaseResponse
from core.inference import BaseInferenceModel, MultiModelData
from core.events import LogEvent

logger = logging.getLogger(__name__)


def _split_kwargs(args_str: str) -> list[str]:
    """Split 'key=val, key2=val2' respecting quotes and parentheses."""
    parts = []
    depth = 0
    current = []
    in_str = None
    for ch in args_str:
        if in_str:
            current.append(ch)
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            current.append(ch)
            in_str = ch
        elif ch in ('(', '[', '{'):
            current.append(ch)
            depth += 1
        elif ch in (')', ']', '}'):
            current.append(ch)
            depth -= 1
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if '=' in p]


class BaseEngine(BaseModel):
    """Base engine model.

    Fields:
    - name, description, model_id, tools
    - response: a BaseResponse instance describing response format
    - history: past interactions
    - system_instructions: optional prompt-level instructions
    """

    model_config = {'arbitrary_types_allowed': True}

    name: str
    description: str
    model_id: BaseInferenceModel
    tools: List[Any] = Field(default_factory=list)
    response: BaseResponse = Field(default=BaseResponse())
    history: List[Any] = Field(default_factory=list)
    system_instructions: str = ''
    multimodal: List[MultiModelData] = Field(default_factory=list)
    tools_description: str = ''
    response_instructions: str = ''

    def model_post_init(self, __context: Any) -> None:
        self.tools_description = self.get_tools_description()
        self.response_instructions = self.response.get_instructions()

    def _tool_name(self, tool: Any) -> str:
        return (
            getattr(tool, '__tool_name__', '')
            or getattr(tool, 'name', '')
            or getattr(tool, '__name__', '')
            or tool.__class__.__name__
        )

    def _tool_description(self, tool: Any) -> str:
        return (
            getattr(tool, '__tool_description__', '')
            or getattr(tool, 'description', '')
            or (inspect.getdoc(tool) or '')
        ).strip()

    def _tool_schema(self, tool: Any) -> Any:
        for attr in (
            '__tool_schema__',
            'input_schema',
            'inputSchema',
            'parameters',
            'schema',
            'args_schema',
            'arguments',
        ):
            value = getattr(tool, attr, None)
            if value not in (None, '', [], {}):
                return value
        return None

    def _format_call(self, tool: Any) -> str:
        name = self._tool_name(tool)
        schema = self._tool_schema(tool)
        if schema and isinstance(schema, dict):
            props = schema.get('properties', {})
            parts = []
            for k, v in props.items():
                if k == 'ctx':
                    continue
                hint = v.get('description', '...') if isinstance(v, dict) else '...'
                parts.append(f'{k}="{hint}"')
            return f'{name}({", ".join(parts)})'
        target = getattr(tool, 'invoke', None) if callable(getattr(tool, 'invoke', None)) else tool
        try:
            sig = inspect.signature(target)
            parts = []
            for p in sig.parameters.values():
                if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                    continue
                if p.default is not inspect.Parameter.empty:
                    continue  # skip optional / internal params
                parts.append(f'{p.name}="..."')
            return f'{name}({", ".join(parts)})'
        except (ValueError, TypeError):
            return f'{name}(...)'

    def get_tools_description(self) -> str:
        if not self.tools:
            return ''
        lines = ['## Tools']
        for tool in self.tools:
            name = self._tool_name(tool)
            desc = self._tool_description(tool)
            # Trim verbose MCP descriptions to first paragraph
            if '\n\n' in desc:
                desc = desc.split('\n\n')[0]
            if '\nArgs:' in desc:
                desc = desc.split('\nArgs:')[0]
            call = self._format_call(tool)
            lines.append(f'{name} - {desc.strip()}')
            lines.append(f'  {call}')
        return '\n'.join(lines)

    def format_history(self) -> str:
        return "\n".join(str(h) for h in self.history)

    def _parse_tool_call(self, call_str: str) -> tuple[str, dict]:
        """Parse 'tool_name(arg=val, ...)' into (name, kwargs).
        Also handles positional args like tool_name("value") by
        mapping them to the tool's parameter names in order."""
        try:
            m = re.match(r'([\w]+)\((.*)\)$', call_str.strip(), re.DOTALL)
            if not m:
                return '', {}
            name = m.group(1)
            args_str = m.group(2).strip()
            if not args_str:
                return name, {}
            kw_parts = _split_kwargs(args_str)
            if kw_parts:
                kwargs = ast.literal_eval('{' + ', '.join(
                    f'"{k.strip()}": {v.strip()}'
                    for part in kw_parts
                    for k, v in [part.split('=', 1)]
                ) + '}')
                return name, kwargs
            # Positional args: try to map to tool parameter names
            tool = self._find_tool(name)
            if tool:
                param_names = getattr(tool, '__tool_params__', None)
                if not param_names:
                    target = getattr(tool, 'invoke', None) if callable(getattr(tool, 'invoke', None)) else tool
                    try:
                        sig = inspect.signature(target)
                        param_names = [p.name for p in sig.parameters.values()
                                       if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
                    except (ValueError, TypeError):
                        param_names = []
                if param_names:
                    try:
                        positional = ast.literal_eval(f'[{args_str}]')
                    except Exception:
                        positional = [args_str.strip('\'"')]
                    kwargs = {}
                    for i, val in enumerate(positional):
                        if i < len(param_names):
                            kwargs[param_names[i]] = val
                    return name, kwargs
            return name, {}
        except Exception:
            return '', {}

    def _find_tool(self, name: str) -> Any:
        for tool in self.tools:
            if self._tool_name(tool) == name:
                return tool
        return None

    def _execute_tool(self, tool: Any, kwargs: dict, on_event=None) -> str:
        name = self._tool_name(tool)
        if on_event:
            on_event(LogEvent(agent=self.name, event_type='tool_call', tool_name=name, input=str(kwargs), status='running'))
        t0 = time.time()
        try:
            if callable(tool):
                result = tool(**kwargs)
            elif hasattr(tool, 'invoke') and callable(tool.invoke):
                result = tool.invoke(**kwargs)
            else:
                return ''
            out = str(result) if result is not None else ''
            elapsed = (time.time() - t0) * 1000
            if on_event:
                on_event(LogEvent(agent=self.name, event_type='tool_result', tool_name=name, output=out[:500], status='success', duration_ms=elapsed))
            return out
        except Exception:
            elapsed = (time.time() - t0) * 1000
            logger.warning('tool execution failed for %s', name, exc_info=True)
            if on_event:
                on_event(LogEvent(agent=self.name, event_type='tool_result', tool_name=name, status='error', duration_ms=elapsed))
            return ''

    def _execute_tools_parallel(self, calls: list[tuple[str, Any, dict]], on_event=None) -> list[tuple[str, str]]:
        """Execute multiple (call_str, tool, kwargs) in parallel. Returns [(call_str, result)]."""
        if len(calls) == 1:
            call_str, tool, kwargs = calls[0]
            return [(call_str, self._execute_tool(tool, kwargs, on_event))]

        results = [None] * len(calls)

        def _run(idx: int, tool: Any, kwargs: dict) -> tuple[int, str]:
            return idx, self._execute_tool(tool, kwargs, on_event)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = {pool.submit(_run, i, t, kw): i for i, (_, t, kw) in enumerate(calls)}
            concurrent.futures.wait(futures)
            for f, idx in futures.items():
                results[idx] = f.result()[1]

        return [(calls[i][0], results[i] or '') for i in range(len(calls))]

    def compose_prompt(self, user_input: str, extra: list = None) -> str:
        sections = []
        if self.system_instructions:
            sections.append(self.system_instructions)
        if self.history:
            sections.append('## History\n' + self.format_history())
        sections.append('## Task\n[human] ' + user_input)
        if extra:
            sections.append('\n'.join(extra))
        if self.tools_description:
            sections.append(self.tools_description)
        if self.response_instructions:
            sections.append(self.response_instructions)
        return '\n\n'.join(sections)

    def invoke(self, user_input: str, multimodal=None, on_event=None) -> str:
        prompt = self.compose_prompt(user_input)
        response = self.model_id.infer(prompt, multimodal or self.multimodal)
        return response or ''


class ReactEngine(BaseEngine):
    max_iterations: int = 10

    def invoke(self, user_input: str, multimodal=None, on_event=None) -> str:
        # working_memory is local to this invocation — tool call/result steps
        # are scratch-pad context only, not persisted to self.history.
        # self.history holds only [human]/[answer] pairs for multi-turn context.
        working_memory: list[str] = []
        parsed = None
        for i in range(self.max_iterations):
            logger.info('react loop iteration %d/%d for %s', i + 1, self.max_iterations, self.name)
            prompt = self.compose_prompt(user_input, extra=working_memory)
            response = self.model_id.infer(prompt, multimodal or self.multimodal) or ''
            parsed = self.response.to_object(response)
            if hasattr(parsed, 'tool_call') and parsed.tool_call:
                calls = []
                for call_str in parsed.tool_call:
                    name, kwargs = self._parse_tool_call(call_str)
                    tool = self._find_tool(name) if name else None
                    if tool:
                        logger.info('calling tool %s with %s', name, kwargs)
                        calls.append((call_str, tool, kwargs))
                    else:
                        working_memory.append(f'[tool_call] {call_str}')
                        working_memory.append('[tool_result] tool not found')
                if calls:
                    results = self._execute_tools_parallel(calls, on_event)
                    for call_str, result in results:
                        working_memory.append(f'[tool_call] {call_str}')
                        working_memory.append(f'[tool_result] {result}')
            else:
                answer = getattr(parsed, 'answer', '') or ''
                if on_event:
                    on_event(LogEvent(agent=self.name, event_type='answer', output=answer[:500], status='success'))
                self.history.append(f'[human] {user_input}')
                self.history.append(f'[answer] {answer}')
                return answer
        answer = (getattr(parsed, 'answer', '') or '') if parsed else ''
        if on_event:
            on_event(LogEvent(agent=self.name, event_type='answer', output=answer[:500], status='success'))
        self.history.append(f'[human] {user_input}')
        self.history.append(f'[answer] {answer}')
        return answer
