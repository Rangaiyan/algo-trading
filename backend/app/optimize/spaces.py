"""Parameter search spaces per strategy (doc 9.3). Ranges stay close to the plan's defaults on purpose:
wide spaces mostly find luck, not edge.

Each entry: ("int", low, high, step) | ("float", low, high, step) | ("cat", [choices]).
"""
from __future__ import annotations

Space = dict[str, tuple]

_EXITS: Space = {"rr": ("float", 1.5, 3.5, 0.25)}
_STRUCT: Space = {"swing_n": ("int", 2, 5, 1), "displacement_k": ("float", 1.0, 2.5, 0.25),
                  "sl_buffer_atr": ("float", 0.1, 0.5, 0.1)}

SPACES: dict[str, Space] = {
    "EMA-1": {**_EXITS, "atr_mult": ("float", 1.0, 2.5, 0.25)},
    "EMA-2": {**_EXITS, "fast": ("int", 8, 30, 2), "slow": ("int", 34, 100, 6), "adx_min": ("int", 15, 35, 5),
              "atr_mult": ("float", 1.0, 3.0, 0.25)},
    "EMA-3": {**_EXITS, "atr_mult": ("float", 0.5, 2.0, 0.25), "fan_bars": ("int", 2, 6, 1)},
    "CANDLE-1": {**_EXITS, "sl_buffer_atr": ("float", 0.0, 0.5, 0.1), "trend_ema": ("int", 100, 250, 50),
                 "patterns": ("cat", [("engulfing", "pin_bar"), ("engulfing",), ("pin_bar",),
                                      ("engulfing", "pin_bar", "star", "tweezer"), ("engulfing", "pin_bar", "inside_breakout")])},
    "SMC-1": {**_STRUCT, "window": ("int", 10, 60, 10), "min_rr": ("float", 1.5, 3.0, 0.25),
              "zone": ("cat", ["ob", "fvg"]), "entry": ("cat", ["edge", "mid"]), "pd_filter": ("cat", [True, False]),
              "use_htf": ("cat", [False, True])},
    "SMC-2": {**_STRUCT, **_EXITS, "pd_filter": ("cat", [True, False]), "use_htf": ("cat", [True, False])},
    "SMC-3": {"fvg_min_atr": ("float", 0.2, 0.8, 0.1), "sl_buffer_atr": ("float", 0.1, 0.5, 0.1), **_EXITS,
              "use_htf": ("cat", [True, False]), "max_wait": ("int", 50, 300, 50)},
    "ICT-1": {**_STRUCT, "window": ("int", 8, 40, 8), "min_rr": ("float", 1.5, 3.0, 0.25),
              "need_displacement": ("cat", [True, False])},
    "ICT-2": {**_STRUCT, "ote": ("float", 0.62, 0.79, 0.01), "target_ext": ("float", 0.0, 0.62, 0.0775),
              "require_fvg": ("cat", [False, True]), "kinds": ("cat", [("CHoCH",), ("CHoCH", "BOS")])},
    "ICT-3": {"fvg_min_atr": ("float", 0.2, 0.8, 0.1), "sl_buffer_atr": ("float", 0.1, 0.5, 0.1), **_EXITS,
              "require_sweep": ("cat", [True, False]), "sweep_lookback": ("int", 10, 80, 10)},
    "ICT-4": {**_STRUCT, "min_rr": ("float", 1.5, 3.0, 0.25), "need_displacement": ("cat", [True, False]),
              "kinds": ("cat", [("BOS", "CHoCH"), ("CHoCH",), ("BOS",)]), "zone": ("cat", ["fvg", "ob"])},
    # rule-builder strategies: tune the confluence threshold, exits and structure settings on top of the spec
    "RULE": {"threshold": ("int", 3, 10, 1), "buffer_atr": ("float", 0.1, 0.5, 0.1), "min_rr": ("float", 1.5, 3.0, 0.25),
             "rr": ("float", 1.5, 3.5, 0.25), "swing_n": ("int", 2, 5, 1), "displacement_k": ("float", 1.0, 2.5, 0.25)},
}


def suggest(trial, space: Space) -> dict:
    out = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "int":
            out[name] = trial.suggest_int(name, spec[1], spec[2], step=spec[3])
        elif kind == "float":
            out[name] = round(trial.suggest_float(name, spec[1], spec[2], step=spec[3]), 6)
        else:
            choices = spec[1]
            pick = trial.suggest_categorical(name, list(range(len(choices))))  # index: choices may be tuples/bools
            out[name] = choices[pick]
    return _fix(out)


def _fix(p: dict) -> dict:
    """Keep combinations valid (e.g. EMA fast < slow); tuples -> lists for JSON."""
    if "fast" in p and "slow" in p and p["fast"] >= p["slow"]:
        p["slow"] = p["fast"] + 10
    return {k: list(v) if isinstance(v, tuple) else v for k, v in p.items()}


def neighbours(params: dict, space: Space) -> list[tuple[str, dict]]:
    """One step down/up for every numeric parameter (doc 10.6 parameter sensitivity)."""
    out = []
    for name, spec in space.items():
        if spec[0] not in ("int", "float") or name not in params:
            continue
        for sign in (-1, 1):
            v = params[name] + sign * spec[3]
            if spec[1] - 1e-9 <= v <= spec[2] + 1e-9:
                p = dict(params)
                p[name] = int(v) if spec[0] == "int" else round(v, 6)
                out.append((f"{name} {'-' if sign < 0 else '+'}{spec[3]}", _fix(p)))
    return out
