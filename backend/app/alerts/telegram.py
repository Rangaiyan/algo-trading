"""Telegram notifier (doc 14). Queue-based, rate-limit aware, allow-listed chats only."""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, token: str, chat_ids: list[str]):
        self.token = token
        self.chat_ids = chat_ids
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_ids)

    async def send(self, text: str, severity: str = "info") -> None:
        if not self.enabled:
            log.info("telegram disabled; dropping message: %s", text[:80])
            return
        await self.queue.put((text, severity))

    async def worker(self) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            while True:
                text, severity = await self.queue.get()
                for chat_id in self.chat_ids:
                    await self._deliver(client, chat_id, text, severity)
                await asyncio.sleep(1.1)  # ~1 msg/sec per chat

    async def _deliver(self, client: httpx.AsyncClient, chat_id: str, text: str, severity: str):
        url = API.format(token=self.token, method="sendMessage")
        payload = {"chat_id": chat_id, "text": text, "disable_notification": severity == "info"}
        for attempt in range(5):
            try:
                r = await client.post(url, json=payload)
                if r.status_code == 429:
                    await asyncio.sleep(r.json().get("parameters", {}).get("retry_after", 2))
                    continue
                r.raise_for_status()
                return
            except Exception:  # noqa: BLE001
                log.warning("telegram send failed (attempt %s)", attempt + 1)
                await asyncio.sleep(2**attempt)

    async def poll_commands(self, status_provider) -> None:
        """Long-poll getUpdates; answer /status and /help for allow-listed chats only."""
        offset = 0
        async with httpx.AsyncClient(timeout=40) as client:
            while True:
                try:
                    r = await client.get(
                        API.format(token=self.token, method="getUpdates"),
                        params={"offset": offset, "timeout": 30},
                    )
                    for upd in r.json().get("result", []):
                        offset = upd["update_id"] + 1
                        msg = upd.get("message") or {}
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        if chat_id not in self.chat_ids:
                            log.warning("ignored command from non-allow-listed chat")
                            continue
                        text = (msg.get("text") or "").strip().split()[0:1]
                        await self._handle(client, chat_id, text[0] if text else "", status_provider)
                except Exception:
                    log.exception("telegram poll error")
                    await asyncio.sleep(5)

    async def _handle(self, client, chat_id, cmd, status_provider):
        if cmd == "/status":
            s = status_provider()
            reply = (
                f"Rinz Algo status\nEnv: {s['environment']}\n"
                f"Live trading: {'ENABLED' if s['live_trading_enabled'] else 'disabled'}\n"
                f"Markets: {', '.join(m['market'] for m in s['markets'] if m['enabled'])}"
            )
        elif cmd == "/help":
            reply = "Commands: /status, /help (more arrive in later phases)"
        else:
            return
        await client.post(
            API.format(token=self.token, method="sendMessage"),
            json={"chat_id": chat_id, "text": reply},
        )
