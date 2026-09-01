# Contributing

## Dev setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium
cd web && pnpm install
```

## Before you push

```bash
ruff check .                 # lint (config in pyproject.toml)
python -m pytest tests/      # fast, no browser/LLM needed
cd web && pnpm build         # typecheck + build the SPA
```

## Guidelines

- Keep the test suite browser-free: engine/judge/parsing logic is tested pure;
  browser behaviour is exercised via `scripts/smoke.py`.
- Schema changes need an Alembic migration (`alembic revision --autogenerate`).
- Commit style: `<type>: <description>` with types
  `feat fix refactor docs test chore perf ci`.
- One logical change per PR, with a short description of the why.
