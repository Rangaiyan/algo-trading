# RINZ ALGO: AI Agent Studio (LangGraph)

**Companion to:** `rinz-algo-project-documentation.md` (extends Section 9.3, Strategy Generator, and Phase 4 of the roadmap)
**Version:** 1.0
**Date:** 13 November 2026
**Orchestration framework:** LangGraph
**LLM provider:** Claude API (Anthropic SDK called inside graph nodes)
**Purpose:** Agents that build trading strategies, review why weak strategies underperform, research fixes, and rebuild them, inside strict guardrails that prevent overfitting and protect real money.

---

## Contents

1. Overview and Scope
2. Core Principles and Hard Rules
3. System Architecture
4. The Agents
5. Graph Design (LangGraph)
6. State Schema
7. Strategy Spec Schema
8. Agent Tools
9. Evaluation and Overfitting Controls
10. Human Approval (Interrupts + Telegram)
11. Checkpointing and Long-Running Jobs
12. Prompts and Output Contracts
13. Budgets and Cost Control
14. Memory: Lineages and Failed-Ideas Archive
15. Database Additions
16. API and Dashboard
17. Observability and Audit
18. Security
19. Project Structure and Dependencies
20. Build Stages and Roadmap Fit
21. Testing Strategy
22. Risks and Mitigations
23. Acceptance Criteria
24. Next Steps
25. Appendix: Code Sketches and Config

---

## 1. Overview and Scope

### 1.1 The idea
Today's strategy generator (Section 9.3 of the main document) searches blindly. The AI Agent Studio adds **reasoning**: a loop in which agents propose a strategy, the platform evaluates it with deterministic code, another agent explains *why* it is weak, another proposes a justified fix, and a critic checks the fix before the next round.

```
Idea → Build → Backtest → (weak?) → Review why → Research fix → Critic → Rebuild → ... → Human approval → Paper trading
```

### 1.2 What it is and is not
| It is | It is not |
|---|---|
| A research assistant that speeds up iteration and documents why ideas work or fail | A guarantee of finding a profitable edge (most ideas will still fail) |
| A controlled loop with caps, budgets, and stop rules | An autonomous trader |
| A producer of validated JSON strategy specs | A writer of arbitrary code that runs unchecked |
| A feeder into the existing stage gates | A way around the stage gates |

### 1.3 Scope
- **In scope:** strategy ideation, review, research, rebuilding (SMC, ICT, EMA, candlestick, combined strategies); failure analysis; lineage tracking; approval via dashboard and Telegram.
- **Out of scope:** live order execution, risk limit changes, broker access, cost-model changes, stage-gate changes. Agents never touch these.

---

## 2. Core Principles and Hard Rules

**Hard rules live in code, never in prompts.** A prompt that says "do not look at the hold-out data" is not a safeguard. The tools simply do not expose it.

| # | Rule | Enforced by |
|---|---|---|
| 1 | **Numbers come from deterministic code.** Agents explain results but never produce or modify them. | Evaluator is plain code; agents get read-only reports |
| 2 | **The hold-out data is invisible to agents.** | Tool layer: no tool accepts or returns hold-out data; the system runs the hold-out test itself |
| 3 | **One hold-out run per lineage.** A failed hold-out retires the lineage; results are never fed back to agents for rebuilding. | Orchestrator + database constraint |
| 4 | **Capped rounds, tokens, and cost.** | Routing functions check budgets |
| 5 | **One change per round**, with a written market-structure rationale. | Output schema allows exactly one change |
| 6 | **Complexity budget.** Maximum blocks and free parameters per spec. | Deterministic validator before backtest |
| 7 | **Every agent output is schema-validated.** Invalid output is rejected and retried within limits. | Structured outputs + Pydantic |
| 8 | **Agents cannot reach brokers, risk settings, or secrets.** | No such tools; separate API key; sandboxing |
| 9 | **A human approves promotion** (backtested → paper). Agents never promote anything. | LangGraph `interrupt()` + approval record |
| 10 | **Everything is logged** (prompts, outputs, versions, costs). | `agent_steps` table and tracing |
| 11 | **Paper trading remains the final judge.** Agent success in backtests proves nothing about the future. | Stage gates (Section 2 of the main document) |

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Dashboard: Agent Studio page   │   Telegram (alerts/approvals)│
└──────────────┬───────────────────────────────┬───────────────┘
               │ REST                          │ bot callbacks
┌──────────────▼───────────────────────────────▼───────────────┐
│                     FastAPI backend                          │
│        /agent-runs   /lineages   /approvals                  │
└──────────────┬───────────────────────────────────────────────┘
               │ enqueue (run_id = LangGraph thread_id)
┌──────────────▼───────────────────────────────────────────────┐
│               Celery worker: LangGraph runtime               │
│                                                              │
│   Builder ─► Validate ─► Evaluator ─► Gate check             │
│      ▲                                   │ weak              │
│      │                                   ▼                   │
│   Critic ◄── Researcher ◄── Reviewer ◄───┘                   │
│                                                              │
│   Gate passed ─► System hold-out test ─► Approval interrupt  │
└──────┬─────────────────┬──────────────────┬──────────────────┘
       │ tools           │ checkpoints      │ Claude API
┌──────▼──────┐   ┌──────▼───────┐   ┌──────▼───────┐
│ Platform    │   │ PostgreSQL   │   │ Anthropic API│
│ services    │   │ (PostgresSaver│  │ (budgeted key)│
│ (backtest,  │   │ + app tables)│   └──────────────┘
│ strategies) │   └──────────────┘
└─────────────┘
```

Key points:
- The **graph runs in a worker**, not in the web process. `thread_id` equals the agent run ID, so any run can be resumed after a restart or an approval.
- Agents reach the platform only through the **tool layer** (Section 8).
- Claude is called with the **Anthropic SDK inside nodes** (Section 12). The graph is the control structure; no agent decides routing or budgets.

---

## 4. The Agents

| Agent | Job | Input | Output (schema-validated) | Suggested model tier* |
|---|---|---|---|---|
| **Builder** | Turn an idea (or a revision instruction) into a strategy spec from the approved block library | Idea text, block library, constraints, previous feedback | `StrategySpec` JSON + rationale | Mid-tier (for example Sonnet) |
| **Reviewer** | Explain *why* a strategy underperforms, using only the evaluation report | Compact `EvalReport` JSON | `ReviewResult`: ranked hypotheses, each citing report numbers | Mid-tier |
| **Researcher** | Propose exactly **one** justified change that tests the top hypothesis | Hypotheses, current spec, lineage history, failed-ideas archive, optional notes | `ChangeProposal` | Top-tier (for example Opus) for hard reasoning |
| **Critic** | Check the proposal for bias, overfit, unrealistic assumptions, repetition | Current spec, proposal, history, deterministic check results | `CriticVerdict` (pass/block + reasons) | Top-tier |
| **Summarizer** (optional, cheap) | Produce run summaries for Telegram and reports | Run log | Short text | Small/fast tier (for example Haiku) |

\*Model names and prices change. Check Anthropic's models page before committing. At the time of writing, the API model strings I have are `claude-opus-5-5`, `claude-sonnet-5-5`, and `claude-haiku-5-5`. Keep model choices in config, not in code.

**The Evaluator is not an agent.** It is deterministic code (backtest + validation) and produces every number.

---

## 5. Graph Design (LangGraph)

### 5.1 Nodes

| Node | Type | Responsibility |
|---|---|---|
| `init` | code | Create/lookup lineage, set budgets, load constraints |
| `builder` | agent | Produce `StrategySpec` |
| `validate_spec` | code | Schema, block/parameter registry, complexity budget, duplicate check |
| `evaluator` | code | Backtest on **train + validation** only; build compact report |
| `gate_check` | code | Compare report to pass criteria (config) |
| `reviewer` | agent | Hypotheses from the report |
| `researcher` | agent | One proposed change |
| `deterministic_checks` | code | Parameter count, change count, similarity to failed ideas, rationale present |
| `critic` | agent | Verdict on the proposal |
| `apply_change` | code | Apply the approved change to the spec (or send back to Builder) |
| `holdout_test` | code | System-run hold-out test (once per lineage) |
| `notify_approval` | code | Send Telegram/dashboard approval request |
| `approval` | human | `interrupt()` waiting for your decision |
| `finalize` | code | Save version, update lineage status, notify, archive lessons |

### 5.2 Flow

```
START → init → builder → validate_spec ──invalid (retry ≤ 2)──► builder
                              │ ok
                              ▼
                          evaluator → gate_check
                              │
              ┌───────────────┼────────────────────┐
         passes gate      weak, budget left     weak, no budget / stop rule
              │                │                       │
              ▼                ▼                       ▼
        holdout_test       reviewer                 finalize (status: not_validated)
              │                │
        ┌─────┴─────┐          ▼
     passes      fails    researcher → deterministic_checks → critic
        │           │                                         │
        ▼           ▼                          ┌──────────────┼───────────┐
 notify_approval  finalize                  pass          block (≤ 2 retries)   block (exhausted)
        │        (lineage retired)             │              │                    │
        ▼                                      ▼              ▼                    ▼
    approval ──reject──► finalize         apply_change    researcher            finalize
        │ approve                              │
        ▼                                      ▼
    finalize                              builder (revised spec) → ...
  (status: validated → eligible for paper trading)
```

### 5.3 Routing rules (in code, not in prompts)

```python
def route_after_gate(state) -> str:
    if state["gate_passed"]:
        return "holdout_test"
    if state["round"] >= state["max_rounds"]:
        return "finalize"                 # stop_reason = "max_rounds"
    if state["cost_usd"] >= state["max_cost_usd"]:
        return "finalize"                 # stop_reason = "budget"
    if state["trials_in_lineage"] >= state["max_trials"]:
        return "finalize"                 # stop_reason = "trial_cap"
    return "reviewer"
```

### 5.4 Stop reasons (always recorded)
`passed_awaiting_approval`, `approved`, `rejected_by_human`, `holdout_failed`, `max_rounds`, `budget`, `trial_cap`, `critic_blocked`, `invalid_spec`, `cancelled`, `error`.

---

## 6. State Schema

LangGraph passes one state object between nodes. Keep it small: store large artifacts (full reports, trade lists) in the database and keep **IDs and compact summaries** in state.

```python
from typing import Annotated, Literal, Optional, TypedDict
from operator import add

class RunState(TypedDict):
    # identity
    run_id: str                      # = thread_id
    lineage_id: str
    idea: str
    family: Literal["smc", "ict", "ema", "candle", "combo"]
    market: Literal["forex", "india"]
    broker_target: Literal["mt5", "oanda", "deriv"]
    symbols: list[str]

    # loop control
    round: int
    max_rounds: int
    trials_in_lineage: int
    max_trials: int
    cost_usd: float
    max_cost_usd: float
    tokens_used: int

    # working data (IDs + compact summaries, not raw data)
    spec: dict                       # current StrategySpec
    spec_version_id: Optional[str]
    report_id: Optional[str]         # evaluation report stored in DB
    report_summary: Optional[dict]   # compact EvalReport used by agents
    gate_passed: bool
    hypotheses: list[dict]
    proposal: Optional[dict]         # ChangeProposal
    critic_verdict: Optional[dict]
    holdout_passed: Optional[bool]   # boolean ONLY; no hold-out metrics in state

    # history (append-only)
    history: Annotated[list[dict], add]   # per-round: spec diff, metrics, hypotheses, change, verdict

    # outcome
    status: str
    stop_reason: Optional[str]
    approval: Optional[dict]
```

Note `holdout_passed` is only a boolean. The hold-out metrics go into the stored report for the **human**, never into state that an agent can read.

---

## 7. Strategy Spec Schema

The Builder outputs a **JSON spec**, not code. The spec uses the building blocks from Section 8 and Section 9 of the main document (sweep, CHoCH/BOS, FVG, OB, premium/discount, sessions, EMA, candle patterns, filters).

```json
{
  "name": "SMC Sweep + CHoCH + FVG (London)",
  "family": "smc",
  "symbols": ["EURUSD", "GBPUSD"],
  "timeframes": { "bias": "H4", "entry": "M15" },
  "filters": {
    "sessions": ["london_kz"],
    "max_spread_pips": 1.5,
    "avoid_news_minutes": { "before": 30, "after": 30 }
  },
  "setup": [
    { "block": "liquidity_sweep", "params": { "levels": ["prev_day_hl", "asia_hl"], "tolerance_atr": 0.2 } },
    { "block": "choch", "params": { "displacement_atr": 1.5 } },
    { "block": "entry_zone", "params": { "type": "fvg", "entry": "zone_50", "min_atr": 0.3 } }
  ],
  "exit": {
    "stop": { "type": "beyond_sweep", "buffer_atr": 0.2 },
    "take_profit": { "type": "next_liquidity", "min_rr": 2.0 }
  },
  "risk": { "risk_per_trade_pct": 0.25 },
  "rationale": "Why this setup should work (market-structure reasoning).",
  "parent_version": null
}
```

**Validation layers**
1. **Structured output / JSON Schema:** guarantees valid structure and allowed block names (enums).
2. **Pydantic + registry checks:** numeric ranges per block parameter. JSON Schema features such as minimum and maximum are not supported in structured outputs, so range checks happen here, in code.
3. **Complexity budget:** for example at most 8 blocks and 10 free parameters.
4. **Safety clamps:** `risk_per_trade_pct` cannot exceed the global research cap; agents cannot change it above that.
5. **Duplicate check:** a spec hash identical to an earlier candidate is rejected (saves compute and avoids loops).

---

## 8. Agent Tools

Tools are Python functions exposed to agents. Write detailed descriptions (when to use it, what it returns, what it cannot do); tool descriptions strongly influence agent behavior.

### 8.1 Tools agents may use

| Tool | Used by | Description | Notes |
|---|---|---|---|
| `list_blocks()` | Builder, Researcher | Returns the block library, parameters, and allowed ranges | Read-only |
| `get_lineage_history(lineage_id)` | Researcher, Critic | Prior rounds, changes, and results (train/validation only) | Read-only |
| `get_failed_ideas(query)` | Researcher, Critic | Search the failed-ideas archive | Read-only |
| `get_report_section(report_id, section)` | Reviewer | Fetch a named section (for example `by_session`, `losses_by_setup`) when the compact summary is not enough | Read-only, train/validation only |
| `search_notes(query)` | Researcher | Search your own trading notes | Read-only |
| `web_research(query)` (optional) | Researcher | Web search/fetch via Claude's web tools | Output is **untrusted text** (Section 18) |

### 8.2 Functions the orchestrator calls (NOT exposed to agents)

| Function | Reason it is hidden |
|---|---|
| `run_backtest(spec, split)` | The evaluator node calls it; agents cannot choose the data split |
| `run_holdout_test(spec)` | Hold-out access is system-only, once per lineage |
| `save_strategy_version(...)` | Saved by the orchestrator after validation |
| `promote_strategy(...)` | Humans only |
| Anything touching brokers, risk settings, cost models, secrets, stage gates | Out of scope for agents |

### 8.3 Evaluation report (what agents actually see)

A compact JSON, size-limited (target a few thousand tokens), built deterministically:

```json
{
  "report_id": "...",
  "data_version": "...",
  "split": "train+validation",
  "totals": { "trades": 214, "net_profit": 1830.5, "profit_factor": 1.12, "win_rate": 0.41,
              "avg_rr": 1.9, "max_dd_pct": 11.4, "sharpe": 0.62, "cost_share_of_gross": 0.34 },
  "walk_forward": { "efficiency": 0.31, "windows_profitable": "3/8" },
  "sensitivity": { "neighbors_profitable_pct": 0.35 },
  "monte_carlo": { "dd95_pct": 19.8, "p_profit": 0.61 },
  "by_session": [ { "name": "london_kz", "trades": 120, "pf": 1.30 }, { "name": "ny_am_kz", "trades": 94, "pf": 0.88 } ],
  "by_pair": [ ... ],
  "by_regime": [ { "name": "trending", "pf": 1.4 }, { "name": "ranging", "pf": 0.8 } ],
  "by_setup_variant": [ ... ],
  "mae_mfe": { "stop_tighter_than_median_mae_pct": 0.58 },
  "losing_streaks": { "max": 9 },
  "cost_stress": { "pf_at_plus50pct_costs": 0.94 },
  "gate_status": { "trades_ok": true, "pf_ok": false, "walkforward_ok": false }
}
```

The hold-out is **never** in this report.

---

## 9. Evaluation and Overfitting Controls

This is the most important part of the design. A faster loop makes overfitting more likely, not less.

### 9.1 Data splits

```
|---- Training ----|---- Validation ----|---- Hold-out (system only) ----|
```

- Agents see results on **training + validation** (the backtest engine uses training for fitting any parameters and validation for checking).
- The **hold-out** is run by the system **once per lineage**, only when the strategy already passes the gate on train + validation.
- If the hold-out fails, the lineage is **retired**. Agents get no hold-out numbers and may not "fix" the strategy using it. A new idea starts a **new lineage**.

### 9.2 Trial counting (multiple-testing awareness)
Every candidate evaluated counts as a trial. Track:
- `trials_in_lineage` and a global trial counter per data period.
- Optionally apply a **trial-adjusted** performance measure (for example a deflated Sharpe-style adjustment) or tighten the gate thresholds as trials increase.

### 9.3 Change discipline
- **One change per round**, so the effect can be attributed.
- Each `ChangeProposal` must include: change type, target, old value, new value, **market-structure rationale**, expected effect, and a self-assessed overfit risk.
- **Allowed change types** (enum): `adjust_param`, `add_filter`, `remove_filter`, `change_exit`, `change_entry_zone`, `change_session`, `restrict_symbol`, `add_confluence_factor`, `remove_block`.
- A change justified only by "this parameter scored higher" is blocked by the Critic.

### 9.4 Complexity penalty
Specs have a **complexity score** (blocks + free parameters). The gate thresholds rise with complexity, and anything over the budget is rejected before backtesting.

### 9.5 Deterministic checks (before the Critic LLM)
- Parameter and block counts within budget.
- Exactly one change in the proposal.
- Rationale present and non-trivial.
- Not a near-duplicate of a failed idea (spec hash and similarity check).
- No new data sources or lookahead-prone blocks (blocks are registry-approved as non-repainting).
- Costs and fill rules unchanged (agents cannot alter them).

### 9.6 Reviewer evidence rule
Every hypothesis must cite **specific report fields and values**. A deterministic validator checks that each cited value matches the report; hypotheses with unverifiable citations are dropped. This prevents agents from inventing numbers.

### 9.7 Critic checklist
Look-ahead or repainting risk, unrealistic fills or costs, curve-fitting signs (very narrow parameter values, many conditions), whether the rationale is market-structure based, whether the change really tests the stated hypothesis, similarity to previously failed ideas, and whether the strategy depends on a single pair or regime without saying so.

### 9.8 Pass criteria (Gate 1)
The gate uses the thresholds from Section 10.6 of the main document (trade count, profit factor net of costs, drawdown, Sharpe/Sortino, walk-forward efficiency, parameter sensitivity, Monte Carlo, cost stress). Thresholds live in **config**, versioned, and agents cannot read or alter them beyond the pass/fail flags shown in the report.

---

## 10. Human Approval (Interrupts + Telegram)

### 10.1 When humans decide
| Decision | Who | When |
|---|---|---|
| Start a run (idea, budgets) | You | Dashboard or Telegram |
| Promote a validated strategy to paper trading | **You** | After the hold-out passes |
| Continue past a soft cap (extra rounds/budget) | You | Optional prompt when a cap is reached |
| Anything touching live trading | You | Outside the Agent Studio entirely |

### 10.2 How it works in LangGraph
LangGraph's `interrupt()` pauses a node, saves state to the checkpointer, and waits. The graph resumes when invoked again with the same `thread_id` and a `Command(resume=...)` payload. A persistent checkpointer is required: without one, `interrupt()` fails, and an in-memory one loses pending approvals on restart. Use **PostgresSaver** in production.

```python
from langgraph.types import interrupt, Command

def notify_approval_node(state):          # separate node: side effects happen here
    telegram.send_approval_request(
        run_id=state["run_id"],
        summary=build_approval_summary(state),   # spec, train/val metrics, hold-out result, rationale history
    )
    return {"status": "awaiting_approval"}

def approval_node(state):
    decision = interrupt({
        "type": "promotion_request",
        "run_id": state["run_id"],
        "lineage_id": state["lineage_id"],
    })
    return {"approval": decision}          # {"decision": "approve"|"reject", "by": "...", "note": "..."}
```

Keep side effects (Telegram sends) in the node **before** the one that calls `interrupt()`. On resume, the interrupted node re-executes from its start, so code before `interrupt()` inside that node must be safe to run twice. Verify the exact behavior against the LangGraph version you pin.

### 10.3 Telegram flow
1. `notify_approval` sends a message with the strategy name, round count, train/validation/hold-out summary, key rationale, and **Approve / Reject / View in dashboard** buttons.
2. Your tap triggers a callback handler (allow-listed chat ID, two-step confirmation for Approve).
3. The handler calls `graph.invoke(Command(resume={...}), config={"configurable": {"thread_id": run_id}})` in a worker.
4. `finalize` records the approval (who, when, note) in the audit log and updates the strategy status: `validated` → eligible for paper trading under the stage gates.

### 10.4 Extra Telegram commands
`/agent_runs` (list), `/agent_status <run_id>`, `/agent_cancel <run_id>`, `/agent_approve <run_id>` (with confirmation), `/agent_budget` (daily spend).

---

## 11. Checkpointing and Long-Running Jobs

- **Checkpointer:** `PostgresSaver` (same PostgreSQL instance, separate schema/tables). LangGraph saves state after each node, enabling resume after restart and approvals that can wait days.
- **Thread ID:** `thread_id = run_id`. One thread per run.
- **Long backtests:** the `evaluator` node submits a backtest job and **polls with a timeout**, or runs it synchronously in the worker. Use a **deterministic job key** (`hash(spec + split + data_version + cost_config)`) so identical candidates return a cached result instead of recomputing.
- **Idempotent nodes:** a node may run more than once after a failure or resume. Side effects (saving versions, sending messages) must use idempotency keys.
- **Time travel / forking (optional):** LangGraph can replay from earlier checkpoints, which helps with debugging; keep it for developers, not as an agent capability.
- **Timeouts for approvals:** if no decision arrives within N days, mark the run `expired` and notify; never auto-approve.

---

## 12. Prompts and Output Contracts

### 12.1 Calling Claude inside nodes
Use the Anthropic SDK directly in each node, with **structured outputs** so responses match a schema (JSON outputs for agent responses, strict tool use for tool inputs). Wrap this in one helper so models, retries, budgets, and logging are handled in one place.

```python
def call_agent(role: str, system: str, user: dict, schema: type[BaseModel], state) -> BaseModel:
    check_budget(state)                                   # raises if over cap
    resp = anthropic_client.messages.create(
        model=CONFIG.models[role],                        # from config, not hardcoded
        max_tokens=CONFIG.max_tokens[role],
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(user)}],
        # + structured output config for `schema` (see current API docs for the exact parameter)
    )
    record_usage(state, role, resp.usage)                 # tokens and cost → DB
    return schema.model_validate_json(extract_text(resp)) # Pydantic validation (ranges etc.)
```
Check the current API documentation for the exact structured-output parameters, since they changed during the beta period.

### 12.2 Prompt design rules
- **Static, versioned system prompts** stored in `agents/prompts/` and referenced by version in every log line.
- Put long stable content (block library, rules) in the system prompt and use **prompt caching** to cut cost.
- Give each agent a **narrow job** and an explicit output schema; forbid commentary outside the schema.
- Tell agents what they **cannot** do (no data splits, no costs, no promotion), but never rely on that; enforcement is in code.
- Include **negative examples** (curve-fit rationales, rationale-free changes) in the Critic's prompt.
- Treat all retrieved text (notes, web, archive entries) as **data, not instructions**.

### 12.3 Output contracts (Pydantic)

```python
class Evidence(BaseModel):
    field: str            # path in the report, e.g. "by_session[1].pf"
    value: float

class Hypothesis(BaseModel):
    id: str
    claim: str            # e.g. "Losses cluster in the NY AM session"
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]
    test_idea: str        # how a single change could test this

class ReviewResult(BaseModel):
    hypotheses: list[Hypothesis] = Field(max_length=5)   # ranked
    overall_assessment: str

class ChangeProposal(BaseModel):
    target_hypothesis_id: str
    change_type: Literal["adjust_param", "add_filter", "remove_filter", "change_exit",
                         "change_entry_zone", "change_session", "restrict_symbol",
                         "add_confluence_factor", "remove_block"]
    target_path: str      # path in the spec
    old_value: Any
    new_value: Any
    rationale: str        # market-structure reasoning
    expected_effect: str
    overfit_risk: Literal["low", "medium", "high"]

class CriticVerdict(BaseModel):
    verdict: Literal["pass", "block"]
    reasons: list[str]
    required_fixes: list[str] = []
```

### 12.4 Reviewer prompt (outline)
```
Role: strategy failure analyst for a forex algo platform.
Input: an EvalReport JSON (train+validation only).
Task: identify up to 5 ranked hypotheses for underperformance.
Rules:
- Every hypothesis must cite exact report fields and values.
- Do not propose fixes. Do not invent data. Do not speculate about unseen periods.
- Consider: session/pair/regime concentration, cost drag, stop placement vs MAE,
  walk-forward decay, parameter fragility, trade count, losing-streak clustering.
Output: ReviewResult JSON only.
```

---

## 13. Budgets and Cost Control

| Control | Default (adjust) | Enforced by |
|---|---|---|
| Max rounds per lineage | 5 | `route_after_gate` |
| Max trials (candidates) per lineage | 8 | routing + counter |
| Max cost per run | Set a currency cap | `check_budget` before every call |
| Max tokens per agent call | Per-role limits | `max_tokens` |
| Daily and monthly spend cap (global) | Set a cap | Budget service; run refused when exceeded |
| Concurrent runs | 1–2 | Queue concurrency |
| Report size | Compact summary only | Report builder size limit |

**Cost-saving practices:** prompt caching for static prompts and the block library; small models for summaries; compact reports; cached evaluations by spec hash; no free-form long conversations between agents.

**Use a separate Anthropic API key** (and spend limit) for Rinz Algo's agents.

Send a Telegram alert at 50%, 80%, and 100% of the daily budget.

---

## 14. Memory: Lineages and Failed-Ideas Archive

### 14.1 Lineages
A **lineage** is one idea and all its rebuilt versions (`v1 → v2 → v3 ...`) with reasons for every change. It provides the audit trail and the trial counter.

Lineage status: `active → gate_passed → holdout_passed → validated → paper → live | retired`.

### 14.2 Failed-ideas archive
When a lineage ends without validation, the `finalize` node saves a structured entry:

```json
{
  "lineage_id": "...",
  "family": "ict",
  "idea_summary": "London KZ Asia range raid with OTE entry",
  "why_failed": ["cost drag too high on M5", "efficiency 0.28 walk-forward", "pair-specific"],
  "changes_tried": ["session filter", "wider SL", "FVG entry"],
  "data_version": "...",
  "stop_reason": "max_rounds"
}
```
Researcher and Critic can search this archive so they do not retry dead ends. Archive entries contain **train/validation facts only**, never hold-out numbers.

### 14.3 Human lessons
You can add manual notes ("what I learned") that agents can search. Keep these separate from agent-written entries.

---

## 15. Database Additions

```
strategy_lineages(id, user_id, family, idea, status, trials, created_at, closed_at, stop_reason)
agent_runs(id, lineage_id, thread_id, status, round, max_rounds, cost_usd, tokens_used,
           started_at, finished_at, stop_reason, config_snapshot_json)
agent_steps(id, run_id, round, node, role, model, prompt_version, input_ref, output_json,
            tokens_in, tokens_out, cost_usd, latency_ms, ts)
hypotheses(id, run_id, round, claim, evidence_json, confidence, test_idea, verified)
change_proposals(id, run_id, round, change_json, critic_verdict_json, applied)
spec_candidates(id, lineage_id, version, spec_hash, spec_json, parent_id, created_at)
evaluation_reports(id, spec_candidate_id, split, report_json, data_version, cost_config_hash, created_at)
holdout_results(id, lineage_id, spec_candidate_id, passed, metrics_json, run_at)   -- UNIQUE(lineage_id)
approvals(id, run_id, decision, decided_by, note, ts, channel)
failed_ideas(id, lineage_id, family, summary, why_failed_json, changes_tried_json, created_at)
agent_budgets(date, spent_usd, cap_usd)
-- LangGraph checkpoint tables are created and managed by PostgresSaver
```

`holdout_results` has a **unique constraint on lineage_id**, which enforces "one hold-out run per lineage" in the database, not just in code. Restrict database permissions so the agent-facing service account cannot read `holdout_results.metrics_json`.

---

## 16. API and Dashboard

### 16.1 Endpoints

```
POST   /agent-runs                 # start: idea, family, symbols, broker_target, budgets
GET    /agent-runs                 GET /agent-runs/{id}
GET    /agent-runs/{id}/steps      # full timeline (prompts/outputs/cost per node)
POST   /agent-runs/{id}/cancel
POST   /agent-runs/{id}/approve    # decision: approve | reject, note   (resumes the graph)
GET    /lineages                   GET /lineages/{id}   # versions, diffs, history
GET    /failed-ideas?query=
GET    /agent-budget               # daily/monthly spend vs caps
```

### 16.2 Dashboard: "Agent Studio" page
- **Start panel:** idea text, strategy family, symbols, target broker, budgets, "Start run".
- **Run timeline:** live graph view highlighting the current node.
- **Round cards:** for each round show the spec **diff**, train/validation metrics, Reviewer hypotheses with their evidence, the proposed change and rationale, the Critic verdict.
- **Lineage view:** version tree with metric trends (watch for improving in-sample numbers with flat walk-forward numbers, a classic overfitting sign).
- **Approval panel:** summary plus hold-out result (human-only view), Approve/Reject with notes.
- **Budget panel:** spend vs caps; alerts.
- **Failed-ideas browser.**

---

## 17. Observability and Audit

- Every node execution writes an `agent_steps` row (input reference, output, tokens, cost, latency, prompt version, model).
- Store enough to **replay** any run: spec hashes, data version, cost config hash, prompt versions, config snapshot.
- Optional tracing tools (for example LangSmith or Langfuse) can add visual traces. Do **not** send secrets or hold-out data to third-party tracing services, and check their data-retention terms.
- Alerts (Telegram): run started/finished, gate passed, hold-out result, approval needed, budget thresholds, repeated schema failures, errors.
- Weekly agent report: runs, pass rates, cost per validated strategy, most common failure reasons.

---

## 18. Security

| Threat | Control |
|---|---|
| Agent reaching brokers/risk/secrets | No such tools; agents run in a service with no broker credentials; separate API key |
| Hold-out leakage | Tool layer exposure rules, DB permissions, `UNIQUE(lineage_id)`, leak tests (Section 21) |
| **Prompt injection** via notes, archive entries, or web content | Treat retrieved text as data; wrap it in clearly delimited blocks; the web-research node has **read-only tools and no write access**; outputs are schema-validated and cannot trigger actions |
| Malformed or malicious outputs | Structured outputs + Pydantic + registry checks; reject and retry within limits |
| Runaway cost | Budgets, caps, daily limits, concurrency limits |
| Code execution risk | **Agents output JSON specs, not code.** If code generation is ever added: Docker sandbox, no network, no secrets, resource limits, human review |
| Unauthorized approvals | Allow-listed Telegram chat IDs, confirmation step, optional PIN/TOTP, audit log |
| Data leakage to the LLM provider | Send only specs and aggregated reports; no account numbers, keys, or personal data; review provider data-handling terms |
| Tampering with prompts/config | Version-controlled prompts and config; changes logged |

---

## 19. Project Structure and Dependencies

```
backend/app/agents/
├── graph.py                 # builds and compiles the LangGraph graph
├── state.py                 # RunState and reducers
├── nodes/
│   ├── init.py  builder.py  validate_spec.py  evaluator.py  gate_check.py
│   ├── reviewer.py  researcher.py  deterministic_checks.py  critic.py
│   ├── apply_change.py  holdout_test.py  notify_approval.py  approval.py  finalize.py
├── routing.py               # route_after_gate, route_after_critic, ...
├── llm.py                   # call_agent helper (models, budgets, usage, retries)
├── schemas.py               # StrategySpec, ReviewResult, ChangeProposal, CriticVerdict
├── tools.py                 # agent-facing tools only (read-only)
├── registry/                # block library, parameter ranges, non-repainting flags
├── budgets.py               # per-run and global spend controls
├── memory/                  # lineages, failed-ideas search, notes search
├── prompts/                 # versioned system prompts (reviewer_v1.md, ...)
├── config.py                # models, caps, thresholds (loaded, versioned)
└── tests/
```

**Key dependencies (pin exact versions; LangGraph's API evolves quickly):**
`langgraph`, `langgraph-checkpoint-postgres`, `anthropic`, `pydantic`, `psycopg`, `celery`, `redis`. Optional: `langchain-anthropic` (only if you prefer LangChain's model wrapper), a tracing client.

---

## 20. Build Stages and Roadmap Fit

The Agent Studio depends on the backtest engine, validation pipeline, strategy library, stage gates, and Telegram service (main document, Phases 1–5). It is built as a **Phase 4b** after the generator basics exist, and it can overlap with the backtest stage only for **research**, never touching live or paper settings.

| Stage | Duration (rough) | Deliverables |
|---|---|---|
| **A: Reviewer-only graph** | 1–2 weeks | LangGraph skeleton, PostgresSaver, `evaluator`, `gate_check`, `reviewer`, `finalize`; report builder; you apply changes manually; Agent Studio page (read-only timeline) |
| **B: Builder loop** | 2 weeks | Builder agent, spec validation, registry, spec hashing/caching, round cap and budgets, lineage tracking |
| **C: Full loop** | 2–3 weeks | Researcher, deterministic checks, Critic, apply_change, system hold-out test, `interrupt()` approvals via dashboard and Telegram, failed-ideas archive |
| **D: Hardening** | 1–2 weeks | Leak tests, budget alarms, replay tools, weekly reports, prompt versioning, load/failure tests |

Stage A gives you an early answer to the key question: **is agent feedback actually useful?** If the Reviewer's hypotheses do not lead to better out-of-sample results, do not proceed to full automation.

**Stage gates stay in charge.** An agent-built strategy enters the same pipeline as any other: `draft → backtested → validated → paper (2 months) → live`, with Gate 1 and Gate 2 criteria unchanged.

---

## 21. Testing Strategy

- **Fake LLM tests:** replace Claude with canned structured outputs to test routing, budgets, retries, and stop reasons deterministically.
- **Routing tests:** every stop reason is reachable; caps stop loops exactly when expected.
- **Leak tests (critical):** automated tests assert that no agent-facing tool, report, state field, archive entry, or log returns hold-out data; attempts to request the hold-out split are rejected.
- **Hold-out once-only test:** a second hold-out run for the same lineage must fail at the database level.
- **Schema fuzzing:** malformed or adversarial agent outputs are rejected, retried within limits, and then end the run cleanly.
- **Evidence verification tests:** hypotheses with wrong or invented numbers are dropped.
- **Interrupt/resume tests:** kill the worker while waiting for approval, restart, resume with `Command(resume=...)`, and confirm no duplicate side effects.
- **Idempotency tests:** re-running a node does not duplicate versions, messages, or charges.
- **Cost tests:** simulated usage hits caps and halts runs; Telegram budget alerts fire.
- **Prompt-injection tests:** poisoned notes/web text cannot change tool use, routing, or output schema.
- **Golden reports:** fixed evaluation reports with expected hypotheses categories for regression checks on prompt changes.
- **Version-pin check:** CI fails when LangGraph/Anthropic SDK versions change unexpectedly; upgrades are tested deliberately.

---

## 22. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Overfitting through repeated rebuilds** | Hold-out lock, one run per lineage, trial counting, round/trial caps, single-change rule, complexity budget, paper trading as final judge |
| Agents invent numbers or evidence | Numbers only from deterministic reports; evidence validator; schema outputs |
| Confident but wrong explanations | Critic checks; the hypothesis must be tested by a single change; you review rounds in the dashboard |
| Cost overruns | Budgets, caps, caching, small models for light tasks |
| Hold-out leakage (even indirectly) | Tool/DB design, permission limits, leak tests, no hold-out numbers in state or archive |
| Prompt injection | Retrieved text treated as data; read-only research node; schema validation |
| Framework changes (LangGraph or SDK) | Pin versions, isolate framework use in `graph.py`/`nodes/`, tests, planned upgrades |
| Stale approvals or duplicate side effects | Idempotency keys, separate notify node, approval timeouts (never auto-approve) |
| Over-trusting the agents | Human approval, stage gates, paper stage, clear UI that agent success is not live evidence |
| Low value of agent feedback | Stage A experiment first; stop if the feedback does not improve out-of-sample results |
| Single-developer maintenance burden | Small number of nodes, clear contracts, strong tests, documentation |

---

## 23. Acceptance Criteria

- A run can be started from the dashboard and Telegram, resumes after a worker restart, and ends with a recorded stop reason.
- All agent outputs are schema-validated; invalid outputs never reach the evaluator or the database as accepted data.
- Agents never receive hold-out data (verified by automated leak tests); hold-out runs exactly once per lineage (database-enforced).
- Round, trial, token, and cost caps stop runs exactly as configured; daily budget alerts work.
- Every round is auditable: spec diff, report, hypotheses with verified evidence, change rationale, critic verdict, tokens, and cost.
- Promotion to paper trading requires a recorded human approval; there is no automatic promotion path.
- Agents have no access to brokers, risk settings, cost models, secrets, or stage gates (verified by tool inventory test).
- Stage A experiment completed and reviewed: documented evidence on whether Reviewer feedback improves out-of-sample results before building Stages B–C.

---

## 24. Next Steps

1. Finish prerequisites: backtest engine, validation pipeline (walk-forward, Monte Carlo, sensitivity), strategy library, stage gates, Telegram notifier.
2. Define the **block registry** (names, parameters, ranges, non-repainting flags) from Section 8 of the main document.
3. Implement the **compact evaluation report** builder and its tests (this is what every agent reads).
4. Create a **separate Anthropic API key** with a spend limit; store it in secrets.
5. Build **Stage A** (Reviewer-only LangGraph graph with PostgresSaver) and run it on a handful of existing strategies.
6. Review the hypotheses with your own trading judgment. Decide whether to continue to Stages B–D.
7. Pin LangGraph and Anthropic SDK versions; read the current LangGraph docs for `StateGraph`, `interrupt`, `Command`, and `PostgresSaver` before coding, since APIs change.

---

## 25. Appendix: Code Sketches and Config

> The sketches are illustrative. Confirm APIs and parameters against the current LangGraph and Anthropic documentation for the versions you pin.

### 25.1 Building and compiling the graph

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

def build_graph(checkpointer):
    g = StateGraph(RunState)

    g.add_node("init", init_node)
    g.add_node("builder", builder_node)
    g.add_node("validate_spec", validate_spec_node)
    g.add_node("evaluator", evaluator_node)            # deterministic
    g.add_node("gate_check", gate_check_node)          # deterministic
    g.add_node("reviewer", reviewer_node)
    g.add_node("researcher", researcher_node)
    g.add_node("deterministic_checks", deterministic_checks_node)
    g.add_node("critic", critic_node)
    g.add_node("apply_change", apply_change_node)
    g.add_node("holdout_test", holdout_test_node)      # system-only
    g.add_node("notify_approval", notify_approval_node)
    g.add_node("approval", approval_node)              # interrupt()
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "init")
    g.add_edge("init", "builder")
    g.add_edge("builder", "validate_spec")
    g.add_conditional_edges("validate_spec", route_after_validate,
                            {"ok": "evaluator", "retry": "builder", "stop": "finalize"})
    g.add_edge("evaluator", "gate_check")
    g.add_conditional_edges("gate_check", route_after_gate,
                            {"holdout": "holdout_test", "review": "reviewer", "stop": "finalize"})
    g.add_edge("reviewer", "researcher")
    g.add_edge("researcher", "deterministic_checks")
    g.add_edge("deterministic_checks", "critic")
    g.add_conditional_edges("critic", route_after_critic,
                            {"apply": "apply_change", "retry": "researcher", "stop": "finalize"})
    g.add_edge("apply_change", "builder")
    g.add_conditional_edges("holdout_test", route_after_holdout,
                            {"approve": "notify_approval", "retire": "finalize"})
    g.add_edge("notify_approval", "approval")
    g.add_edge("approval", "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)

# Worker startup
with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    checkpointer.setup()
    graph = build_graph(checkpointer)
    config = {"configurable": {"thread_id": run_id}}
    graph.invoke(initial_state, config)
```

### 25.2 Resuming after approval

```python
from langgraph.types import Command

graph.invoke(
    Command(resume={"decision": "approve", "by": "rinz", "note": "Looks consistent"}),
    config={"configurable": {"thread_id": run_id}},
)
```

### 25.3 Evaluator node (deterministic, cached)

```python
def evaluator_node(state):
    key = spec_hash(state["spec"], split="train+validation",
                    data_version=DATA_VERSION, cost_hash=COST_HASH)
    report = report_cache.get(key) or backtest_service.run(
        spec=state["spec"], split="train+validation")      # splits chosen HERE, never by an agent
    summary = build_compact_report(report)                  # size-limited, no hold-out
    return {
        "report_id": report.id,
        "report_summary": summary,
        "trials_in_lineage": state["trials_in_lineage"] + 1,
        "round": state["round"] + 1,
        "history": [{"round": state["round"] + 1, "spec_hash": key, "metrics": summary["totals"]}],
    }
```

### 25.4 Example config (YAML)

```yaml
agent_studio:
  models:                       # verify names/prices on Anthropic's models page
    builder:    claude-sonnet-5-5
    reviewer:   claude-sonnet-5-5
    researcher: claude-opus-5-5
    critic:     claude-opus-5-5
    summarizer: claude-haiku-5-5
  limits:
    max_rounds: 5
    max_trials_per_lineage: 8
    max_cost_usd_per_run: 10          # set to your own budget
    daily_cap_usd: 25
    max_tokens: { builder: 4000, reviewer: 3000, researcher: 3000, critic: 2000, summarizer: 800 }
    max_blocks_per_spec: 8
    max_free_params_per_spec: 10
    schema_retry_limit: 2
    critic_retry_limit: 2
  research_caps:
    max_risk_per_trade_pct: 0.5       # agents cannot exceed this in specs
  gate:                               # mirrors Section 10.6 of the main document; versioned
    min_trades: 100
    min_profit_factor_net: 1.3
    max_drawdown_pct: 15
    min_sharpe: 1.0
    min_walk_forward_efficiency: 0.5
    min_neighbors_profitable_pct: 0.6
    cost_stress_plus_pct: 50
  approval:
    require_human: true
    expire_after_days: 7
    telegram_confirmation: true
  data:
    holdout_visible_to_agents: false  # not a runtime switch; enforced in code, listed for documentation
```

### 25.5 Glossary

| Term | Meaning |
|---|---|
| **LangGraph** | Framework for building stateful, cyclic agent workflows as graphs of nodes and edges |
| **Node / Edge** | A step (function) in the graph / the routing between steps |
| **Checkpointer** | Component that saves graph state after each step (PostgresSaver in production) |
| **Thread ID** | Identifier of one run's saved state; used to resume |
| **`interrupt()`** | LangGraph primitive that pauses a node and waits for external input |
| **Lineage** | One strategy idea and all its rebuilt versions |
| **Trial** | One evaluated candidate; counted for multiple-testing awareness |
| **Hold-out** | Final untouched data block, run once by the system |
| **Structured outputs** | Claude API feature that constrains responses to a JSON schema |
| **Prompt injection** | Malicious text in retrieved content that tries to steer the model |

---

*Disclaimer: This is a technical design, not financial advice. Agent-assisted research can still produce strategies that fail in live trading. Backtested and paper results do not guarantee future performance.*
