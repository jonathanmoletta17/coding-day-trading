# AI Learned Summary: Coding Day Trading

**Generated:** 2026-01-02
**Scope:** Deep analysis of repository structure, architecture, and governance.

## 1. System Architecture & Context

### Hybrid Runtime Environment
The system operates on a **split-architecture pattern** necessitated by the MetaTrader 5 (MT5) dependency:
- **Windows Host**: Runs the `MT5 Bridge API` (FastAPI) and the proprietary MT5 Terminal. Acts as the "hardware driver" for market access.
- **WSL/Linux**: Runs the "Brain" — `Data Collectors`, `TimescaleDB`, `DSL Engine`, and `Analysis Modules`.
- **Communication**: REST (Command/Control) and WebSocket (Tick Streaming) over local network (localhost:8000).

### Core Components
| Component | Path | Responsibility | Tech Stack |
|-----------|------|----------------|------------|
| **MT5 Bridge** | `infrastructure/mt5_bridge_service.py` | Exposes MT5 via HTTP/WS. | Python, FastAPI, win32 |
| **DSL Engine** | `src/microstructure/dsl_v01.py` | Deterministic event pattern matching. | Python, Custom Lexer/Parser |
| **Context Classifier** | `src/analysis/market_context_classifier.py` | Statistical behavior analysis. | Pandas, SQL, Dataclasses |
| **Data Collector** | `infrastructure/mt5_data_collector.py` | Ingests data to TimescaleDB. | Python, AsyncIO |

## 2. Technical Philosophy & Patterns

### The "No-Prediction" Doctrine
The system is explicitly designed **NOT to predict price**.
- **Evidence**: `Market Context Classifier` docstrings explicitly state "NÃO gera sinais" and "NÃO prevê preços".
- **Focus**: Descriptive analysis of *what happened* (Activity) and *how market reacted* (Behavior).
- **Metric**: "Sweeps per day", "Reversion Rate", not "Expected Profit".

### Deterministic Microstructure (DSL)
- **Engine**: A custom Domain Specific Language (DSL) v0.1.
- **Mechanism**: Event stream processing (`SEQUENCE`, `ALL_OF`, `ANY_OF`) with strict windowing (`WITHIN 500ms`).
- **Goal**: To identify liquidity patterns (Sweeps, Block Trades) mathematically, removing subjective interpretation.

### Governance as Code
The project treats governance as a compilation error:
- **Frozen Rules**: `REGRAS_CONGELADAS.md` defines immutable laws (e.g., "Separate experiments from src").
- **Execution Contract**: `CONTRATO_DE_EXECUCAO.md` mandates a 7-step state machine for task execution.
- **Canonical Truths**: `PROJECT_CONTEXT.yaml` serves as the single source of truth for what constitutes "Production".

## 3. Critical Validation Metrics

### For Code Changes
1.  **Zero-Impact Proof**: Changes to non-production areas must be proven via `grep` or file lists to touch *nothing* in `src/`.
2.  **Test Completeness**: Unit tests must exist for any logic in `src/`. Integration tests (`test_end_to_end.py`) must pass for infrastructure changes.
3.  **Import Integrity**: No circular imports allowed. Strict separation between `infrastructure` (runtime) and `src` (logic).

### For Market Logic
1.  ** Determinism**: Same input inputs must yield exactly the same output.
2.  **Auditability**: Every classified context (High Activity / Reversive) must be traceable to specific tabular metrics.

## 4. Key Learnings for Future Agents

- **Don't Touch Windows Files from Linux**: You cannot run `mt5_bridge_service.py` in the Linux environment. It mocks or fails.
- **Respect the Boundary**: `experiments/` is a "safe zone". `src/` is "production/money-at-risk". Changes to `src/` require rigorous protocol.
- **DSL Syntax**: It's custom. Don't invent syntax. Stick to `PATTERN`, `REQUIRE`, `MATCH`, `EMIT`.
- **Database**: It's TimescaleDB (PostgreSQL extension). Use time-series queries.

## 5. Potential Improvements Detected
- **Dashboard Gap**: The project mentions a missing implementation of the Visualization Dashboard (`src/visualization`).
- **Test Coverage**: While `src/microstructure` has unit tests, the `Market Context Classifier` relies on ad-hoc script execution.
- **CI/CD**: Local Docker composition is strong, but no robust CI pipeline definition was observed (reliant on local scripts).
