"""Telegram channel stub.

Wire up a real Telegram bot by filling in start() and handle_update()
with any Telegram client library (e.g. python-telegram-bot or aiogram).
The channel owns the I/O loop; Gateway handles all agent logic.
"""
from core.gateway import Gateway


class TelegramChannel:
    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def start(self) -> None:
        """Start the Telegram bot polling loop."""

    def handle_update(self, update: dict) -> str:
        """Process one incoming Telegram update and return the agent reply."""
        message = (update.get('message') or {}).get('text') or ''
        return self.gateway.run(message) if message else ''
