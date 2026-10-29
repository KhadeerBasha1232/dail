"""Tiny Telegram Bot API client (HTML messages, inline buttons, long polling)."""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("jobbot.telegram")


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token: str, client: httpx.AsyncClient):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.client = client

    async def call(self, method: str, http_timeout: float = 30, **params):
        params = {k: v for k, v in params.items() if v is not None}
        for attempt in range(3):
            try:
                r = await self.client.post(self.base + method, json=params, timeout=http_timeout)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise TelegramError(f"{method}: {e}") from e
                await asyncio.sleep(2)
                continue
            data = r.json()
            if data.get("ok"):
                return data["result"]
            retry = (data.get("parameters") or {}).get("retry_after")
            if r.status_code == 429 and retry:
                log.warning("Telegram flood limit, waiting %ss", retry)
                await asyncio.sleep(retry + 1)
                continue
            raise TelegramError(f"{method}: {data.get('description')}")
        raise TelegramError(f"{method}: gave up")

    async def send(self, chat_id, text: str, buttons: list | None = None, preview: bool = False):
        return await self.call(
            "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
            link_preview_options={"is_disabled": not preview},
            reply_markup={"inline_keyboard": buttons} if buttons else None)

    async def edit_text(self, chat_id, message_id: int, text: str, buttons: list | None = None):
        try:
            return await self.call(
                "editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                parse_mode="HTML", link_preview_options={"is_disabled": True},
                reply_markup={"inline_keyboard": buttons} if buttons else None)
        except TelegramError as e:
            if "not modified" not in str(e):
                raise

    async def edit_buttons(self, chat_id, message_id: int, buttons: list | None):
        try:
            return await self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                                   reply_markup={"inline_keyboard": buttons or []})
        except TelegramError as e:
            if "not modified" not in str(e):
                raise

    async def answer(self, callback_id: str, text: str = "", alert: bool = False):
        try:
            await self.call("answerCallbackQuery", callback_query_id=callback_id, text=text, show_alert=alert)
        except TelegramError as e:
            log.info("answerCallbackQuery: %s", e)

    async def updates(self, offset: int | None, timeout: int = 25) -> list:
        return await self.call("getUpdates", http_timeout=timeout + 10, offset=offset, timeout=timeout,
                               allowed_updates=["message", "channel_post", "callback_query"])

    async def set_commands(self, commands: list[tuple[str, str]]):
        await self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in commands])
