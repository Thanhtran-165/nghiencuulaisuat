# Contributing

Thanks for your interest in improving this project.

## Development setup

- Backend (Python): see `README.md`
- Frontend (Next.js): see `frontend/README.md`

## How to contribute

1. Fork the repo and create a feature branch.
2. Make focused changes with small commits.
3. Run tests locally:
   - `docker compose run --rm app pytest -q`
   - `cd frontend && npm ci && npm run typecheck` (or `npx tsc -p tsconfig.json --noEmit`)
4. Open a PR with:
   - what changed
   - how to verify
   - screenshots for UI changes (if relevant)

## Coding guidelines

- Prefer small, targeted fixes.
- Keep provider changes isolated and add tests where possible.
- Avoid committing generated data: `data/`, `logs/`, `*.duckdb`, `.env`.

