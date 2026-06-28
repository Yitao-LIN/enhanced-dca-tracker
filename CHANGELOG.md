# Changelog

## v0.1.0 - Local release candidate

- Added backend-persisted manual transaction entry for buy, sell, dividend, fee, and cash-outflow rows.
- Added security search for manual transaction ticker selection and Fortuneo mapping workflows.
- Kept duplicate-safe Fortuneo CSV/ZIP preview and import flows.
- Added allocation analytics, benchmark comparison, hidden securities, ticker deletion/re-import, and saved DCA plans.
- Moved the frontend to a Vite React app with a sidebar workflow.
- Added Windows and Linux/WSL launchers for backend, frontend, and tests.
- Improved daily and intraday portfolio history so the latest prior market quote carries forward to newer manual transactions.
- Documented release setup, testing, architecture, and first-release checks.
