"""Gateway — the single entry point between input channels and the agent engine.

All input channels (CLI, web, Telegram, …) call gateway.run() with a message
and optional multimodal data. The gateway forwards to the underlying engine
and returns the text answer.
"""
from typing import Any, Callable

from core.engine import BaseEngine
from core.inference import MultiModelData


class Gateway:
    def __init__(self, engine: BaseEngine) -> None:
        self.engine = engine

    def run(
        self,
        message: str,
        multimodal: list[MultiModelData] | None = None,
        on_event: Callable[[Any], None] | None = None,
    ) -> str:
        return self.engine.invoke(message, multimodal=multimodal, on_event=on_event)
