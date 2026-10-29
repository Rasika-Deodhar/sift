.PHONY: setup dev backend frontend test lint fixtures reels

PY := backend/.venv/bin/python

setup:
	cd backend && (command -v uv >/dev/null && uv venv -q .venv && uv pip install -q -p .venv/bin/python -e ".[dev]" \
	  || (python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"))
	cd frontend && npm install --silent

backend/.venv:
	$(MAKE) setup

frontend/node_modules:
	cd frontend && npm install --silent

# Runs the API on :8000 and the web app on :5173. Open http://localhost:5173
# (Sift) and http://localhost:5173/demo/ (Demo Feed) in two windows.
dev: backend/.venv frontend/node_modules
	@trap 'kill 0' EXIT INT TERM; \
	(cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload) & \
	(cd frontend && npx vite --port 5173) & \
	wait

backend: backend/.venv
	cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload

frontend: frontend/node_modules
	cd frontend && npx vite --port 5173

test: backend/.venv frontend/node_modules
	cd backend && .venv/bin/pytest -q
	cd frontend && npx vitest run

lint: backend/.venv frontend/node_modules
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npx tsc -b

# Re-record scene-change fixtures from the Demo Feed (needs Playwright + a running backend).
fixtures:
	node frontend/scripts/record-fixtures.mjs

reels:
	python3 demo_feed/tools/make_reels.py
