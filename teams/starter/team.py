"""Starter team: orchestrator delegates to web_search, command_line, and chrome."""
from core.loader import load_agent
from core.engine import BaseEngine


def build() -> BaseEngine:
    web_search = load_agent('agents/web_search')
    command_line = load_agent('agents/command_line')
    chrome = load_agent('agents/chrome')

    orchestrator = load_agent(
        'agents/orchestrator',
        agent_engines={
            'web_search': web_search,
            'command_line': command_line,
            'chrome': chrome,
        },
    )
    return orchestrator
