# CLAUDE.md

## Project
"THE MAIN OCR" - Consignor/Consignee OCR. FastAPI + Motor (MongoDB) backend, PaddleOCR / PP-StructureV3 for OCR, Groq LLM for field extraction. Two separate Vite/React apps: `frontend/` (users) and `admin/` (admin console). A document = Part 1 (consignee/consignor header) + Part 2 (line items + tax summary) uploaded as a pair. Git `origin` = OCR-CONSIGNOR-CONSIGNEE-BILL-AI. Never commit or push unless asked in that turn.

## Commands
Backend (from `backend/`, repo-root `venv`; runtime pins in root `requirements.txt`, dev tools in `requirements-dev.txt`):
- Run: `uvicorn app.main:app --reload`. Tests: `pytest` (tests sit next to the code as `test_*.py`). One test: `pytest app/features/ocr/test_extraction.py::test_name`.
- Lint: `ruff check .`, `black .`, `isort .` (line length 100, py312). Types: `mypy .` (untyped defs not allowed).
- Tests never touch a real database: `conftest.py` forces a `*_test` DB name, aborts otherwise, and installs an in-process fake Mongo (`fake_mongo.py`). Never weaken that guard. Use `testkit.py` (`make_user`, `make_document`, `current_db`). Real-server run: set `TEST_MONGO_URI` to a `*_test` database only. If a pipeline stage is missing in `fake_mongo.py`, extend it minimally.
- Scripts: `python -m app.scripts.seed_admin` (admins come from `ADMIN_*` env vars), `python -m app.scripts.migrate_user_status [--dry-run]`.
Frontend / admin (each has its own `package.json`): `npm run dev`, `npm run build`, `npm run lint`. Browser checks (mocked backend): `node e2e/<file>.cjs` in `frontend/e2e/`.

## Architecture
- `app/core/` config, DB, security, audit log. `app/features/` auth, admin (cross-user, `require_admin`), documents (user routes), ocr (pipeline).
- Wire format and Mongo field names are camelCase (Pydantic `CamelModel`); Python is snake_case. Lists serialize raw Mongo dicts through `_serialize_document`.
- OCR: Part 1 = `ocr/pipeline.py:process_part1` (OpenCV preprocessing, flat PaddleOCR, column bucketing, Groq). Part 2 = `ocr/table_extraction.py:process_part2` (PP-StructureV3 tables, `table_html_parser`, Groq for the tax summary). **Part 2 must get the raw image: never apply Part 1 preprocessing to it** (it shifts empty cells and breaks the column alignment).
- Only page 1 of a PDF is read (PDFs up to 4 pages are accepted; the review page shows a note).
- `ocr/extraction.py` is pure deterministic correction (digit/letter confusion, GSTIN, PAN, date, money). The pipeline and manual edits (`correction_service.py`) both use it. Do not duplicate it.
- OCR jobs share one slot (`ocr/ocr_slot.py`). A hung OCR thread holds it until restart (accepted).

## Documents - rules to keep
- Every user query is scoped `{"userId": current_user.id, "isDeleted": {"$ne": True}}`. Malformed id = 400; not yours / not found = 404, never 403.
- List query lives in `documents/list_query.py` (search over invoice no / consignee code / consignee, strict `YYYY-MM-DD` date, month, IST `range`, `needsReview`, `status`, server-side `sort`/`order` with `_id` tie-breaker). `needs_review_condition()` is the one rule shared with `/stats`: never copy it.
- Stored flags, no migration of old rows: `hasLowConfidenceFields`, `hasReviewWarnings` (set when processing ends and recomputed in the same guarded update after every correction), `processingRunId`.
- Pipeline writes only if `{"_id", "processingRunId"}` still matches (stale jobs are ignored). Reprocess claims the document atomically (409 if already processing; a claim older than 30 min counts as stuck).
- Delete is permanent (record + GridFS files + corrections). "Delete files" (purge) removes both originals but keeps the extracted data; both routes (user and admin) use `documents/file_purge.py`.
- Download All: `POST /documents/download-all` with ids. Max 30 ids and 100 MB, one running download per user, zip built on disk, unique folder names, audited. `/documents/stats` and `/documents/storage` feed the dashboard.
- Upload limits: 5 MB per file, bulk max 5 sets, filenames and invoice numbers go through `core/filenames.py` before use in headers or zip entries.
- Restart recovery (`documents/recovery.py`) re-queues documents stuck in `processing`.

## Security (follow, do not reinvent)
- `get_current_user` re-reads the user from Mongo on every request: approval gate (`status` must be `approved`, a missing field = legacy = approved) and `tokenVersion` check (this is how forced logout works). JWT is HS256 only, 7-day TTL.
- Signup creates `pending`; admins approve / reject / revoke. Login checks the password first, then reveals pending / rejected.
- Email is admin-only. Passwords: 8-64 bytes, mixed case + digit + special, not common, not containing the username or email part (new passwords only).
- Admin opening another user's document or file writes an audit entry BEFORE returning data; if the audit write fails, the request fails.
- Rate limiting (slowapi) applies to auth routes only. `/docs` is off unless `ENABLE_DOCS=true`. 422 responses never echo the input.

## Frontend
- The URL query string is the source of truth for list filters and paging (`frontend/src/lib/documentFilters.js`); server data goes through React Query (`hooks/` -> `api/`). Zustand is for auth and dialogs only.
- `src/api/client.js` (both apps): `baseURL: "/api"`, adds the bearer token, global 401 -> logout.
- After any mutation that changes a document, invalidate `["documents"]` so the list, stats and storage refresh (default `staleTime` is 10 s).

## Known and accepted
Forgot-password works for admins too; sessions last 7 days; a waiting OCR job is not re-checked; a hung OCR thread holds the slot until restart.
