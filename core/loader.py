from pathlib import Path
from typing import Any, Callable
import asyncio
import logging

from core.engine import BaseEngine, ReactEngine
from core.inference import get_inference_model
from core.responses import BaseResponse, ReActResponse
from core.tools import MCPServerConfig, get_mcp_tools

logger = logging.getLogger(__name__)


def _parse_agent_md(md_path: Path) -> tuple[dict[str, Any], str]:
	text = md_path.read_text(encoding='utf-8') if md_path.exists() else ''
	if not text.strip().startswith('---'):
		return {}, text

	lines = text.splitlines()
	try:
		end = lines[1:].index('---') + 1
	except ValueError:
		return {}, text

	frontmatter_text = '\n'.join(lines[1:end])
	body = '\n'.join(lines[end + 1:]).strip()

	try:
		import yaml

		meta = yaml.safe_load(frontmatter_text) or {}
	except Exception:
		meta = {}
	return meta, body


def _load_tool_functions(tools_py_path: Path, tool_names: list[str]) -> list[Callable[..., Any]]:
	if not tools_py_path.exists() or not tool_names:
		return []

	try:
		import importlib.util

		spec = importlib.util.spec_from_file_location('agent_tools', tools_py_path)
		if spec is None or spec.loader is None:
			return []

		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)

		return [getattr(module, name) for name in tool_names if callable(getattr(module, name, None))]
	except Exception:
		return []


def _get_engine(logic_name: str) -> type[BaseEngine]:
	if (logic_name or '').lower() == 'react':
		return ReactEngine
	return BaseEngine


def _get_response(logic_name: str, format_name: str) -> BaseResponse:
	logic = (logic_name or '').lower()
	format_type = (format_name or '').lower()

	if format_type == 'react_json':
		logic = 'react'
		format_type = 'json'
	elif format_type == 'react':
		logic = 'react'
		format_type = 'toon'

	if format_type not in ('json', 'toon'):
		format_type = 'toon'

	if logic == 'react':
		return ReActResponse(response_type=format_type)
	return BaseResponse(response_type=format_type)


def load_agent(agent_dir: str, agent_engines: dict[str, BaseEngine] | None = None) -> BaseEngine:
	path = Path(agent_dir)
	if not path.exists():
		path = Path('agents') / agent_dir
	meta, system_instructions = _parse_agent_md(path / 'agent.md')
	logic = meta.get('logic', '')
	model_kwargs = meta.get('model_kwargs', {})
	if not isinstance(model_kwargs, dict):
		model_kwargs = {}

	tool_names = meta.get('tools', [])
	if not isinstance(tool_names, list):
		tool_names = []

	tools = []
	if meta.get('mcp'):
		mcp_config = MCPServerConfig(**meta['mcp'])
		if tool_names:
			mcp_config.include_tools = tool_names
		tools = get_mcp_tools(mcp_config)
	else:
		func_tools = _load_tool_functions(path / 'tools.py', tool_names)
		func_names = {getattr(f, '__name__', '') for f in func_tools}
		tools.extend(func_tools)
		if agent_engines:
			for name in tool_names:
				if name not in func_names and name in agent_engines:
					tools.append(agent_engines[name])

	engine_cls = _get_engine(logic)

	return engine_cls(
		name=meta.get('name', path.name),
		description=meta.get('description', ''),
		model_id=get_inference_model(meta.get('model', ''), **model_kwargs),
		tools=tools,
		response=_get_response(logic, meta.get('response_format', 'toon')),
		system_instructions=system_instructions,
	)


def list_agents(agents_dir: str = 'agents') -> list[str]:
	path = Path(agents_dir)
	if not path.exists():
		return []
	return sorted([item.name for item in path.iterdir() if item.is_dir() and (item / 'agent.md').exists()])


async def load_team(team_dir: str, agents_dir: str = 'agents') -> BaseEngine:
	path = Path(team_dir)
	if not path.exists():
		path = Path('teams') / team_dir

	meta, body = _parse_agent_md(path / 'team.md')
	orchestrator_name = meta.get('orchestrator', '')
	agent_names = meta.get('agents', [])
	if not isinstance(agent_names, list):
		agent_names = []

	# Load member agents
	agents = {}
	for name in agent_names:
		try:
			agents[name] = load_agent(str(Path(agents_dir) / name))
			logger.info('loaded_agent=%s', name)
		except Exception:
			logger.warning('failed to load agent=%s', name, exc_info=True)

	# Load orchestrator with agent registry so its tool names resolve to engines
	orchestrator = load_agent(str(Path(agents_dir) / orchestrator_name), agent_engines=agents)
	logger.info('loaded_team=%s orchestrator=%s agents=%s', meta.get('name', path.name), orchestrator_name, list(agents.keys()))
	return orchestrator
