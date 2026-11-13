import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.telegram import TelegramNotifier
from app.api.account import router as account_router
from app.api.backtests import router as backtests_router
from app.api.ledger import router as ledger_router
from app.api.routes import router, system_status
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    notifier = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id_list)
    app.state.notifier = notifier
    tasks = []
    if notifier.enabled:
        tasks = [
            asyncio.create_task(notifier.worker()),
            asyncio.create_task(notifier.poll_commands(system_status)),
        ]
        await notifier.send("Rinz Algo backend started", severity="info")
    yield
    for t in tasks:
        t.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Rinz Algo", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(backtests_router)
    app.include_router(ledger_router)
    app.include_router(account_router)
    return app


app = create_app()
