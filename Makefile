.PHONY: help install test agent dev seed follow-up clean

help:
	@echo "RAI — comandos disponibles:"
	@echo "  make install      — instala dependencias del agent"
	@echo "  make test         — corre tests del agent"
	@echo "  make dev          — arranca el agent en modo desarrollo"
	@echo "  make simulate     — simulador CLI (sin Twilio)"
	@echo "  make seed         — pobla la BD con 5 leads de muestra"
	@echo "  make follow-up    — ejecuta el job de seguimientos (dry-run)"
	@echo "  make clean        — limpia caches y bd local"

install:
	pip install -r apps/agent/requirements.txt

test:
	cd apps/agent && python -m pytest tests/ -v

dev:
	cd apps/agent && uvicorn app.main:app --reload --port 8000

simulate:
	cd apps/agent && python scripts/simulate.py

seed:
	cd apps/agent && python scripts/seed_demo_data.py

follow-up:
	cd apps/agent && python scripts/follow_up.py --dry-run

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -f apps/agent/data/rai.db apps/agent/data/rai.db-journal
