"""Gate 0 API: status of the MT5 Strategy Tester output file and the trade-by-trade comparison."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.mt5_history import Gateway, GatewayError
from app.gates import gate0

router = APIRouter(prefix="/gate0", tags=["gate0"])


class CompareIn(BaseModel):
    csv: str | None = None            # uploaded file content; default = the EA's file in MT5's Common folder
    server_offset_hours: float | None = None


def _offset() -> float:
    try:
        return float(Gateway(timeout=10).status().get("server_utc_offset_hours") or 0.0)
    except GatewayError:
        return 0.0


@router.get("/info")
def info() -> dict:
    return gate0.file_info() | {"tolerances": gate0.TOL, "ea_source": "mt5-gateway/mql5/RinzGate0.mq5"}


@router.post("/compare")
def compare(req: CompareIn) -> dict:
    text = req.csv
    if not text:
        p = Path(gate0.DEFAULT_FILE)
        if not p.exists():
            raise HTTPException(404, f"No tester output yet at {p}. Run RinzGate0 in the MT5 Strategy Tester first.")
        text = p.read_text(errors="replace")
    try:
        return gate0.compare(text, req.server_offset_hours if req.server_offset_hours is not None else _offset())
    except (ValueError, FileNotFoundError, KeyError) as e:
        raise HTTPException(422, str(e)) from e
