# Release Checklist

Use this before tagging or sharing a local release with other users.

## v0.1 Local Release Gate

- Confirm the repository is on the intended release branch and has no unrelated local changes.
- Run backend setup on Windows:
  - `cd backend`
  - `python -m venv .venv`
  - `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Run backend setup on Linux/WSL:
  - `cd backend`
  - `python3 -m venv .venv`
  - `./.venv/bin/python -m pip install -r requirements.txt`
- Run frontend setup:
  - `cd frontend`
  - `npm install`
- Run automated checks:
  - Windows: `.\run_tests.bat`
  - Linux/WSL: `./run_tests.sh`
- Run frontend build when Node dependencies are available:
  - `npm --prefix frontend run build`
- Smoke test the local app:
  - backend at `http://127.0.0.1:8000`
  - frontend at `http://127.0.0.1:5173`
  - manual transaction add and duplicate retry
  - Fortuneo CSV/ZIP preview and confirmed import
  - security mapping search and confirmed mapping import
  - market-history backfill and portfolio chart
  - analytics target save and DCA recommendation
- Confirm docs match the shipped workflow:
  - `README.md`
  - `docs/ARCHITECTURE.md`
  - `docs/TESTING.md`
  - `CHANGELOG.md`
- Back up or reset `.local/tracker-dev.sqlite3` before recording demos or screenshots.

## Known v0.1 Limits

- Local single-user workflow only.
- Manual cash transactions are cash outflows only.
- The frontend requires Node/Vite for development and build.
- Market search and backfill depend on provider availability and network access.
- No authentication, hosted deployment, or packaged installer yet.
