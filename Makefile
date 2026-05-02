.PHONY: help setup backend-setup frontend-setup \
        dev backend-dev frontend-dev \
        start stop status restart \
        config config-init config-show \
        typecheck backend-typecheck frontend-typecheck \
        docs gen-steps-doc gen-third-party e2e clean-tests \
        mac-app clean

help:
	@echo "DataInsightGrove tasks:"
	@echo ""
	@echo "  Setup"
	@echo "    make setup              One-time: backend venv + pnpm install"
	@echo ""
	@echo "  Run / lifecycle"
	@echo "    make start              Start backend + web detached, write PID file"
	@echo "    make stop               Graceful stop"
	@echo "    make status             Show whether services are up + URLs"
	@echo "    make restart            stop then start"
	@echo "    make dev                Run both in foreground (Ctrl-C to stop)"
	@echo "    make backend-dev        Backend only, foreground"
	@echo "    make frontend-dev       Frontend only, foreground"
	@echo ""
	@echo "  Custom ports"
	@echo "    ./scripts/dig-start.sh --api-port 9000 --web-port 4000"
	@echo "    ./scripts/dig-start.sh --api-port 9000 --save     # persist to config"
	@echo ""
	@echo "  Config"
	@echo "    make config-init        Write a default config.json"
	@echo "    make config-show        Print effective config"
	@echo "    ./scripts/dig_config.py set api.port 9000"
	@echo "    ./scripts/dig_config.py get web.port"
	@echo ""
	@echo "  Quality"
	@echo "    make typecheck          Both backend + frontend"
	@echo ""
	@echo "  Mac app"
	@echo "    make mac-app            Build DataInsightGrove.app (Mac only; Xcode CLT)"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean              Remove venv, node_modules, build artifacts"

setup: backend-setup frontend-setup

backend-setup:
	cd backend && python3 -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install -e '.[dev]'

frontend-setup:
	pnpm install

# ---- foreground (developer) ----

dev:
	./scripts/dig-dev.sh

backend-dev:
	cd backend && DIG_RELOAD=1 .venv/bin/dig-api

frontend-dev:
	cd frontend && pnpm dev

# ---- detached (lifecycle) ----

start:
	./scripts/dig-start.sh

stop:
	./scripts/dig-stop.sh

status:
	@./scripts/dig-status.sh || true

restart: stop start

# ---- config ----

config: config-show

config-init:
	./scripts/dig_config.py init

config-show:
	./scripts/dig_config.py show

# ---- quality ----

typecheck: backend-typecheck frontend-typecheck

backend-typecheck:
	cd backend && .venv/bin/python -c "import dig; from dig.api.main import app; print('backend imports ok')"
	@if [ -x backend/.venv/bin/mypy ]; then cd backend && .venv/bin/mypy dig; fi

frontend-typecheck:
	cd frontend && pnpm exec tsc --noEmit

# ---- docs ----

docs: gen-steps-doc gen-third-party

gen-steps-doc:
	python3 scripts/gen-steps-doc.py

# Regenerate THIRD_PARTY.md from the live dep tree. Needs the backend venv
# active so importlib.metadata can walk the installed Python packages.
gen-third-party:
	@if [ ! -d backend/.venv ]; then \
		echo "✗ backend/.venv missing — run \`make setup\` first"; exit 1; \
	fi
	. backend/.venv/bin/activate && python3 scripts/gen-third-party.py

# ---- E2E validation ----

e2e:
	@echo "Make sure DIG is running (make start) before running this."
	python3 scripts/e2e_validate.py

# Bulk-delete test/leftover pipelines + datasets (e2e:* by default).
# Defaults to DRY-RUN; pass APPLY=1 to actually delete.
clean-tests:
	@if [ "$(APPLY)" = "1" ]; then \
		python3 scripts/cleanup-test-pipelines.py --apply; \
	else \
		python3 scripts/cleanup-test-pipelines.py; \
		echo ""; \
		echo "  → re-run with APPLY=1 to actually delete: make clean-tests APPLY=1"; \
	fi

# ---- Mac app ----

mac-app:
	./mac/build.sh

linux-install:
	./linux/install.sh

# ---- cleanup ----

clean:
	rm -rf backend/.venv backend/**/__pycache__ backend/**/*.pyc backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
	rm -rf frontend/node_modules frontend/.next frontend/out
	rm -rf node_modules
	rm -rf mac/build
