# Working on this RTLS workspace

## Scope and layout

- `rtls-backend/` and `rtls-frontend/` are **separate Git repositories**. Run Git commands inside the relevant directory and check each working tree before editing. The workspace root, this file, and `plans/` are outside those repositories.
- Read the component README before changing its startup, configuration or contracts. `README.md` at the workspace root connects the two components.
- `arduino/` contains hardware sketches. The software baseline uses four fixed anchors A0–A3 and one mobile tag T0; only A0 feeds the USB gateway.
- `plans/rtls-roadmap.md` describes future work, not implemented functionality or permission to implement every step. `plans/rtls-audit-2026-09-08.md` records an audit snapshot, not a passing certification.

## Trace the real data flow

`tools/mauwb_gateway.py` → MQTT `rtls/ranges` → `rtls/engine.py` → PostgreSQL and MQTT `rtls/positions/{tag}` → `rtls/api.py` → REST/WebSocket → frontend `src/store.ts` and `src/lib/api.ts` → React/SVG.

- Backend: configuration in `rtls/config.py`; solver/filter in `rtls/positioning/`; initial schema in `sql/schema.sql`. There is no migration runner, authentication layer or calibration API.
- Frontend: geometry/flags in `src/config.ts`; replay/statistics in `src/lib/trajectory.ts`; transparent analysis rules in `src/lib/insights.ts`. No LLM or `/insights` endpoint is implemented.
- Reuse this stack and existing helpers. Trace all callers before fixing a shared function. Prefer a focused change and an existing dependency or native control over a new abstraction.

## Contracts to preserve

- Coordinates and distances use metres. X is depth from the entrance; Y is width; Z is height. Surveyed anchor coordinates live in PostgreSQL, while zones are currently frontend constants.
- Gateway range scale defaults to `0.01` (centimetres to metres). Keep height, range tolerance and filter calibration adjustable; hardware assumptions need measurements.
- MQTT timestamps must carry a timezone. REST consumers send ISO UTC and the UI displays browser-local time. Reject invalid/non-finite values at input boundaries.
- Raw `ranges` support diagnosis; `positions` are derived. Do not silently remove data or replace rejected measurements with invented positions. RMS is a solver residual, not measured positional accuracy.
- A cycle should yield at most one accepted position in the running engine. Rejected positions must not mutate filter state. Current deduplication is in memory, not durable exactly-once processing.
- Demo data must require `VITE_DEMO=true`. A failed real connection must never switch to demo. The frontend demo has six synthetic anchors and three tags; it is not the physical five-board installation.
- Preserve stale/disconnected states, tag/period identity for asynchronous history, and gaps in replay. Current continuity limits target walking, not arbitrary moving objects.
- Keep keyboard access, labels, focus indicators and reduced-motion behavior when editing UI. User-facing text is Spanish; keep UTF-8 intact.

## Verification

From `rtls-frontend/`:

```powershell
npm.cmd ci
npm.cmd test
npm.cmd run build
```

Only install when dependencies are missing or the lockfile changed. `npm` is equivalent on shells without PowerShell's `npm.ps1` restriction. Tests use Node's test runner and `tests/load.cjs`; UI hook mocks/static rendering are not browser coverage.

From `rtls-backend/`, with a working installed Python environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Backend tests mock database/MQTT but exercise the real numerical solver. If the interpreter does not launch, report the check as blocked; do not call that a test failure or pass. Virtual environments are machine-local and must not be committed.

For meaningful logic changes, add the smallest regression check that fails for the bug. Run the relevant suite and frontend build when appropriate. Connection/recovery changes also need a disposable PostgreSQL/MQTT integration trial. Hardware accuracy requires actual boards and surveyed ground truth; simulations cannot establish it.

## Data and delivery

- Inspect and preserve unrelated changes. Do not commit `.env`, virtual environments, build output, credentials, or employee-location captures.
- Schema initialization runs only on a new PostgreSQL volume. Use an explicit migration for existing data. `docker compose down -v` destroys the database; do not use it as routine troubleshooting.
- Current broker/database defaults are for a controlled development environment. Do not broaden network access as part of a routine fix. Security work must cover REST, WebSocket and MQTT, not just frontend controls or CORS.
- For an audit, report severity, trigger, evidence, impact and a concrete next check; distinguish observed behavior from inference. Do not silently turn an audit into a remediation project.
- Before editing a README, ask yourself: does someone installing, configuring or using the project need this information to complete a task or understand its behavior? Update it only when the answer is yes. Keep agent permissions, internal workflows, implementation notes and work summaries out of the README; put necessary agent instructions in AGENTS.md and report completed work in the response. Do not add documentation merely because a file or command changed.
- Report checks actually run and unresolved limitations. Commit/push only when the task authorizes it.
