"""Tests for agent loading, tool execution, and prompt formatting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engine import BaseEngine, ReactEngine, _split_kwargs
from core.responses import BaseResponse, ReActResponse
from core.inference import BaseInferenceModel
from core.loader import load_agent, list_agents, load_team
from core.gateway import Gateway


def test_split_kwargs():
    assert _split_kwargs('command="ls -la"') == ['command="ls -la"']
    assert _split_kwargs('a="hello", b="world"') == ['a="hello"', 'b="world"']
    assert _split_kwargs('x="(1,2)", y="3"') == ['x="(1,2)"', 'y="3"']
    assert _split_kwargs('') == []
    print('PASS: test_split_kwargs')


def test_parse_tool_call():
    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
    )
    name, kwargs = engine._parse_tool_call('run_command(command="ls -la")')
    assert name == 'run_command'
    assert kwargs == {'command': 'ls -la'}

    name, kwargs = engine._parse_tool_call('foo()')
    assert name == 'foo'
    assert kwargs == {}

    name, kwargs = engine._parse_tool_call('bad input')
    assert name == ''
    assert kwargs == {}
    print('PASS: test_parse_tool_call')


def test_tool_execution():
    def echo(text: str) -> str:
        return f'echo: {text}'

    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        tools=[echo],
    )
    tool = engine._find_tool('echo')
    assert tool is not None
    result = engine._execute_tool(tool, {'text': 'hello'})
    assert result == 'echo: hello'

    assert engine._find_tool('nonexistent') is None
    print('PASS: test_tool_execution')


def test_tools_description_format():
    def run_command(command: str) -> str:
        """Executes a shell command."""
        return command

    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        tools=[run_command],
    )
    desc = engine.get_tools_description()
    assert '## Tools' in desc
    assert 'run_command - Executes a shell command.' in desc
    assert 'run_command(command="...")' in desc
    assert '### `' not in desc
    assert 'Input schema:' not in desc
    print('PASS: test_tools_description_format')


def test_compose_prompt():
    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        system_instructions='You are a test agent.',
    )
    prompt = engine.compose_prompt('hello')
    assert '## Task' in prompt
    assert '[human] hello' in prompt
    assert 'You are a test agent.' in prompt
    assert '## History' not in prompt
    print('PASS: test_compose_prompt')


def test_compose_prompt_with_history():
    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        system_instructions='You are a test agent.',
        history=['[tool_call] echo(text="hello")', '[tool_result] echo: hello'],
    )
    prompt = engine.compose_prompt('follow up')
    assert '## History' in prompt
    assert '[tool_call] echo(text="hello")' in prompt
    assert '[tool_result] echo: hello' in prompt
    assert '[human] follow up' in prompt
    print('PASS: test_compose_prompt_with_history')


def test_load_agent_command_line():
    agent = load_agent('agents/command_line')
    assert agent.name == 'command_line'
    assert len(agent.tools) == 1
    assert agent._tool_name(agent.tools[0]) == 'run_command'
    print('PASS: test_load_agent_command_line')


def test_load_agent_orchestrator_without_registry():
    agent = load_agent('agents/orchestrator')
    assert agent.name == 'orchestrator'
    assert len(agent.tools) == 0
    print('PASS: test_load_agent_orchestrator_without_registry')


def test_load_agent_orchestrator_with_registry():
    cmd = load_agent('agents/command_line')
    agent = load_agent('agents/orchestrator', agent_engines={'command_line': cmd})
    assert agent.name == 'orchestrator'
    assert len(agent.tools) == 1
    tool = agent.tools[0]
    assert agent._tool_name(tool) == 'command_line'
    assert isinstance(tool, BaseEngine)
    print('PASS: test_load_agent_orchestrator_with_registry')


def test_engine_as_tool():
    inner = BaseEngine(
        name='inner_agent', description='An inner agent.',
        model_id=BaseInferenceModel(model='test'),
    )
    outer = BaseEngine(
        name='outer', description='outer',
        model_id=BaseInferenceModel(model='test'),
        tools=[inner],
    )
    assert outer._tool_name(inner) == 'inner_agent'
    assert outer._tool_description(inner) == 'An inner agent.'
    desc = outer.get_tools_description()
    assert 'inner_agent - An inner agent.' in desc
    assert 'inner_agent(user_input="...")' in desc
    print('PASS: test_engine_as_tool')


def test_list_agents():
    agents = list_agents()
    assert 'command_line' in agents
    assert 'orchestrator' in agents
    assert 'chrome' in agents
    assert 'web_search' in agents
    print('PASS: test_list_agents')


def test_parallel_tool_execution():
    import time as _time

    def slow_a(x: str) -> str:
        _time.sleep(0.2)
        return f'a:{x}'

    def slow_b(x: str) -> str:
        _time.sleep(0.2)
        return f'b:{x}'

    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        tools=[slow_a, slow_b],
    )
    calls = [
        ('slow_a(x="1")', slow_a, {'x': '1'}),
        ('slow_b(x="2")', slow_b, {'x': '2'}),
    ]
    t0 = _time.time()
    results = engine._execute_tools_parallel(calls)
    elapsed = _time.time() - t0
    assert results == [('slow_a(x="1")', 'a:1'), ('slow_b(x="2")', 'b:2')]
    # Parallel should take ~0.2s not ~0.4s
    assert elapsed < 0.35, f'took {elapsed:.2f}s, expected parallel'
    print('PASS: test_parallel_tool_execution')


def test_react_response_toon():
    resp = ReActResponse(response_type='toon')
    text = 'observation=(user wants files)\nthinking=(delegate to command_line)\ntool_call=(command_line(task="list files"))\nanswer='
    parsed = resp.to_object(text)
    assert parsed.tool_call == ['command_line(task="list files")']
    assert parsed.answer == ''
    print('PASS: test_react_response_toon')


def test_react_response_json():
    import json
    resp = ReActResponse(response_type='json')
    text = json.dumps({
        'observation': ['user wants files'],
        'thinking': ['delegate to command_line'],
        'tool_call': ['command_line(task="list files")'],
        'answer': ''
    })
    parsed = resp.to_object(text)
    assert parsed.tool_call == ['command_line(task="list files")']
    assert parsed.answer == ''
    print('PASS: test_react_response_json')


def test_gateway():
    def echo(text: str) -> str:
        return f'echo:{text}'

    engine = BaseEngine(
        name='test', description='test',
        model_id=BaseInferenceModel(model='test'),
        tools=[echo],
    )
    gw = Gateway(engine)
    # Gateway.run() routes to engine.invoke()
    assert gw.engine is engine
    print('PASS: test_gateway')


if __name__ == '__main__':
    test_split_kwargs()
    test_parse_tool_call()
    test_tool_execution()
    test_tools_description_format()
    test_compose_prompt()
    test_compose_prompt_with_history()
    test_load_agent_command_line()
    test_load_agent_orchestrator_without_registry()
    test_load_agent_orchestrator_with_registry()
    test_engine_as_tool()
    test_list_agents()
    test_parallel_tool_execution()
    test_gateway()
    test_react_response_toon()
    test_react_response_json()
    print('\nAll tests passed.')
