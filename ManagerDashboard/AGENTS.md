# AGENTS.md

Guidance for coding agents working in this repository.

## Project Overview

This directory is `ManagerDashboard`, the operator/admin server and main game engine for S-Future-Conference.

- Runtime: Python 3.14
- Web stack: FastAPI, Starlette, Uvicorn
- Realtime layer: `python-socketio` in ASGI mode
- Core data libraries: pandas, numpy
- File watching: watchdog
- Default local port: `3003`

The runtime entry point is `server.py`. The main game rules and settlement logic live in `game_engine.py`. The admin UI is served from `index.html`.

## Repository Layout

- `server.py`: FastAPI + Socket.IO server, HTTP routes, event handlers, CSV watcher setup.
- `game_engine.py`: `BPGameEngine` and the main settlement/business logic.
- `index.html`: Admin dashboard UI.
- `requirements.txt`: Python dependencies.
- `Dockerfile`: Container build for the admin service.
- `main.py`: Auxiliary script.

## Data Contract

This service shares CSV files with the sibling V2 module under `../V2/data/`.

Important files include:

- `Teams.csv.csv`
- `Holdings.csv.csv`
- `Subsidiarys.csv.csv`
- `BP_TradeOrder.csv`

When changing logic that reads or writes these files:

- Preserve `utf-8-sig` CSV encoding unless intentionally migrating all dependent services.
- Treat column names as part of the external contract. Common required columns include `Team`, `capital`, `price`, `total asset`, `parent`, and `subsidiary`.
- Be careful with concurrent reads/writes because V2 and other services may access the same CSVs.
- Do not reset, truncate, or rewrite `BP_TradeOrder.csv` casually. Order processing depends on `last_order_idx` and append-style accumulation.

## Development Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
python server.py
```

The server should bind to `0.0.0.0:3003` and serve the dashboard at `http://localhost:3003`.

Before running locally, make sure `../V2/data/` exists and contains realistic CSV data. The directory may be created automatically, but empty or malformed CSVs will not exercise the real game flow.

## Implementation Notes

- Keep `server.py` focused on transport concerns: HTTP routes, Socket.IO events, status broadcasts, and watcher lifecycle.
- Keep settlement, scoring, backups, rollback, subsidiaries, sabotage, forced trade, and mini-game reward logic in `game_engine.py`.
- Preserve in-memory state assumptions unless deliberately redesigning lifecycle behavior. Important state includes big-game running status, round backup history, and `last_order_idx`.
- If changing hardcoded team mappings or secret keys, check for matching constants in sibling services such as StockGame/V2 and update them together when required.
- Avoid broad refactors during event-operation fixes. This code is operationally sensitive because it coordinates live game state.

## Verification

For narrow Python changes, at minimum run:

```bash
python -m py_compile server.py game_engine.py main.py
```

For behavior touching CSV settlement or Socket.IO events, also perform a local smoke test:

```bash
python server.py
```

Then open the dashboard and verify that startup, status events, and CSV-dependent flows behave correctly with test data.

## Operational Cautions

- Docker/compose integration may require path review. The service expects `../V2/data/` relative to its working directory.
- Server restart clears in-memory progress flags, backup history, and order index state.
- Round rollback depends on backup history created during the same process lifetime.
- Manual CSV edits during a live event can desynchronize game state.
