from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtest import runner

router = APIRouter(prefix="/backtests")


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    source: str = Field("synthetic", pattern="^(synthetic|store)$")
    days: int = Field(150, ge=10, le=2000)
    params: dict = {}
    risk_pct: float = Field(0.5, gt=0, le=5)
    cost_stress: float = Field(1.0, ge=1.0, le=3.0)
    commission_per_lot: float = Field(0.0, ge=0)


@router.get("/strategies")
def list_strategies() -> list[dict]:
    return [{"id": k, "name": v.__doc__.strip().split("\n")[0] if v.__doc__ else k}
            for k, v in runner.STRATEGIES.items()]


@router.post("")
def create_backtest(req: BacktestRequest) -> dict:
    try:
        return runner.run(**req.model_dump())
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except (StopIteration, FileNotFoundError) as e:
        raise HTTPException(404, "unknown symbol or no stored data for it") from e
