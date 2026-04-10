from typing import Any, Callable
import asyncio
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run a coroutine, handling both inside and outside an existing event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class MCPServerConfig(BaseModel):
    name: str = ''
    command: str = ''
    args: list[str] = Field(default_factory=list)
    env: dict[str, Any] = Field(default_factory=dict)
    cwd: str = ''
    description: str = ''
    include_tools: list[str] = Field(default_factory=list)


def filter_tools(tools: list[Any], include_tools: list[str]) -> list[Any]:
    if not include_tools:
        return list(tools or [])

    allowed = set(include_tools)
    return [tool for tool in (tools or []) if (getattr(tool, 'name', '') or getattr(tool, '__name__', '')) in allowed]


def _wrap_tool(client: Any, tool: Any) -> Callable[..., Any]:
    name = getattr(tool, 'name', '') or getattr(tool, '__name__', 'tool')
    description = getattr(tool, 'description', '') or ''
    schema = getattr(tool, 'inputSchema', None) or getattr(tool, 'input_schema', None)

    def wrapped(**kwargs):
        try:
            async def _call():
                async with client:
                    return await client.call_tool(name, kwargs or {})

            result = _run_async(_call())
            if hasattr(result, 'content') and isinstance(result.content, list):
                return '\n'.join(getattr(item, 'text', str(item)) for item in result.content)
            if isinstance(result, list):
                return '\n'.join(getattr(item, 'text', str(item)) for item in result)
            return str(result) if result is not None else ''
        except Exception:
            logger.warning('mcp tool call failed for %s', name, exc_info=True)
            return ''

    wrapped.__name__ = name
    wrapped.__doc__ = description
    wrapped.__tool_name__ = name
    wrapped.__tool_description__ = description
    wrapped.__tool_schema__ = schema
    wrapped.__tool_raw__ = tool
    wrapped.__tool_params__ = [k for k in (schema or {}).get('properties', {}).keys() if k != 'ctx'] if schema else []
    return wrapped


def get_mcp_tools(config: MCPServerConfig) -> list[Callable[..., Any]]:
    if not config.command:
        return []

    try:
        from fastmcp.client import Client
        from fastmcp.client.transports import StdioTransport

        transport = StdioTransport(
            command=config.command,
            args=config.args,
            env={k: str(v) for k, v in config.env.items()} if config.env else None,
            cwd=config.cwd or None,
        )
        client = Client(transport)

        async def _list():
            async with client:
                return await client.list_tools()

        available_tools = _run_async(_list())
        selected_tools = filter_tools(available_tools, config.include_tools)
        return [_wrap_tool(client, tool) for tool in selected_tools]
    except Exception:
        logger.warning('failed to load mcp tools for %s', config.command, exc_info=True)
        return []