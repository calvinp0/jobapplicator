.PHONY: dev api web

dev:
	./scripts/dev.sh

api:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd frontend && VITE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host localhost --port 5173
