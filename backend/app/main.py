import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.telegram import TelegramNotifier
from app.api.account import router as account_router
from app.api.backtests import data_router
from app.api.backtests import router as backtests_router
from app.api.ledger import router as ledger_router
from app.api.routes import router, system_status
from app.api.gate0 import router as gate0_router
from app.api.optimize import router as phase3_router
from app.api.structure import router as structure_router
from app.api.trading import router as trading_router
from app.core.access import ORIGIN_REGEX, AccessTokenMiddleware
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    notifier = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id_list)
    app.state.notifier = notifier
    tasks = []
    handler = None
    if s.mt5_gateway_url and s.trading_engine_enabled:
        from app.api.trading import command_handler, run_loop
        tasks.append(asyncio.create_task(run_loop(notifier)))  # Phase 5 trading engine (demo-only orders)
        handler = command_handler().handle
    if notifier.enabled:
        tasks += [
            asyncio.create_task(notifier.worker()),
            asyncio.create_task(notifier.poll_commands(system_status, handler)),
        ]
        await notifier.send("Rinz Algo backend started", severity="info")
    yield
    for t in tasks:
        t.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Rinz Algo", version="0.1.0", lifespan=lifespan)
    # CORS must wrap the token check so a 401 still carries CORS headers (added last = outermost).
    app.add_middleware(AccessTokenMiddleware, token=get_settings().app_access_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ORIGIN_REGEX,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(backtests_router)
    app.include_router(ledger_router)
    app.include_router(account_router)
    app.include_router(data_router)
    app.include_router(structure_router)
    app.include_router(phase3_router)
    app.include_router(trading_router)
    app.include_router(gate0_router)
    return app


app = create_app()
