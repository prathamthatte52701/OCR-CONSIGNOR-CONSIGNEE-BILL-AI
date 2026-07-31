# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"THE MAIN OCR" — Consignor/Consignee OCR system. FastAPI + Motor (async MongoDB) backend that OCRs uploaded documents (PaddleOCR/PP-StructureV3) and extracts structured fields via Groq LLM. Two separate React/Vite frontends: `frontend/` (end-user app) and `admin/` (admin console). Not a git repo at present.

## Commands

Backend (from `backend/`, using the repo-root `venv`):
- Run server: `uvicorn app.main:app --reload`
- Run all tests: `pytest` (testpaths = `app`, tests live as `test_*.py` siblings next to the code they cover, not in a separate `tests/` dir)
- Run a single test: `pytest app/features/ocr/test_extraction.py::test_name`
- Lint/format: `ruff check .`, `black .`, `isort .` (configured in `backend/pyproject.toml`, line-length 100, py312)
- Type check: `mypy .` (`disallow_untyped_defs = true`)

Frontend / admin (from `frontend/` or `admin/`, each is an independent Vite app with its own `package.json`):
- Dev server: `npm run dev`
- Build: `npm run build`
- Lint: `npm run lint`

Python dependencies are declared in a single `requirements.txt` at the repo root (not inside `backend/`).

## Architecture

### Backend layout
- `app/main.py` — FastAPI entrypoint; mounts `auth_router` (`/api/auth`), `admin_router` (`/api/admin`), `documents_router` (`/api/documents`); registers the slowapi rate-limit handler.
- `app/core/` — config, DB connection, JWT/security helpers, rate limiting, audit logging, shared validators.
- `app/features/auth/` — signup/login/token endpoints.
- `app/features/documents/` — user-facing upload/list/edit/delete routes; this is where the OCR pipeline gets invoked.
- `app/features/admin/` — cross-user admin routes (`require_admin` dependency), separate from the user-scoped document routes.
- `app/features/ocr/` — the OCR/extraction pipeline itself (see below).

Mongo documents use `MongoBaseModel`/`CamelModel` (`app/core/base_model.py`): Pydantic models with `alias_generator=to_camel`, so Python fields are snake_case but the wire format (and Mongo field names) are camelCase (`created_at` ↔ `createdAt`). The document-list endpoint doesn't validate through the full `Document` model — it serializes raw Mongo dicts via `_serialize_document`.

### OCR pipeline — Part 1 vs Part 2
Documents have two parts with genuinely different processing paths, orchestrated together by `app/features/documents/processing.py:run_full_pipeline`, called from the upload endpoint's background task and the reprocess endpoint (`app/features/documents/router.py`):

- **Part 1** (header-style document): `app/features/ocr/pipeline.py:process_part1`. Flow: `preprocessing.assess_and_preprocess` (OpenCV, quality-gated) → `paddle_runner.run_ocr` (flat `PaddleOCR` engine) → `split_into_columns` (buckets OCR boxes by x-coordinate, not an image-level crop) → `extract_part1_header` (Groq).
- **Part 2** (line-items table): `app/features/ocr/table_extraction.py:process_part2`. Flow: raw image (no OpenCV preprocessing — see below) → `ppstructure_runner.analyze_page` (`PPStructureV3` table engine) → `table_html_parser` (`parse_table_rows`/`find_item_rows`) → `build_line_items` → `extract_part2_summary` (Groq, tax-summary section only).
- **Part 2 deliberately skips `preprocessing.py`.** `table_extraction.py` has a comment explaining why: generic OpenCV preprocessing (deskew/CLAHE/lighting-normalize) was confirmed on real samples to shift empty-cell positions and corrupt PP-Structure's column alignment. PP-Structure has its own internal doc-orientation classification, so Part 2 gets the raw image. Any new preprocessing work must respect this Part 1/Part 2 split — don't apply Part 1-style preprocessing unconditionally to Part 2.
- Region isolation (header region for Part 1, table region for Part 2) is delegated entirely to PP-StructureV3's built-in layout analysis for Part 2, and to text-level column bucketing for Part 1 — there is no manual image-crop step anywhere in the pipeline today.
- PaddleOCR/PP-StructureV3 config (`paddle_runner.py`, `ppstructure_runner.py`): CPU-only PaddleX 3.x API, mobile models, `use_doc_orientation_classify=True` (page-level orientation IS enabled) but `use_textline_orientation=False` and `use_doc_unwarping=False`.
- Timeouts: Part 1 OCR 60s (image) / 180s (PDF) (`paddle_runner.py`); Part 2 table extraction 300s (image) / 420s (PDF, PP-Structure loads more sub-models) (`table_extraction.py`); Groq LLM call itself 60s (`groq_provider.py`). All enforced via `asyncio.wait_for`.

### Character-confusion correction layer — treat as a stable, separate concern
`app/features/ocr/extraction.py` is pure deterministic post-processing (no OCR/AI calls): digit/letter confusion maps, `correct_gstin`, `correct_pan`, `correct_invoice_no`, `correct_date`, `correct_money`, etc., dispatched via `correct_field` against per-field-class maps (`PART1_FIELD_CLASSES`, `LINE_ITEM_FIELD_CLASSES`, `PART2_SUMMARY_FIELD_CLASSES`). It's applied automatically inside `run_full_pipeline` (`processing.py:_apply_corrections`) and reused by the manual-edit path in `correction_service.py:apply_field_correction` — both the automatic pipeline and user-driven field edits route through the same correction logic rather than duplicating it.

### Document list endpoint — query shape
`GET /api/documents` (`app/features/documents/router.py:list_documents`): filters are `invoiceNo`/`consigneeCode` (case-insensitive regex) and `date` (substring regex against the string field `challanDate` — not a real date range). Pagination is classic skip/limit (`page`, `limit`, default 30, max 100). Sort is hardcoded `createdAt` descending, no client-controllable sort. There is no `documentType` concept anywhere in the model.

Separately, `purge_range`/`purge_all` (documents) and `delete_user` (admin) build their own independent unpaginated Mongo queries (`.to_list(length=None)`) against the same `documents` collection for bulk-delete purposes — they don't share query-building code with `list_documents`, so changes to one don't affect the other, but keep it that way.

### Security patterns (already established — follow, don't reinvent)
- Every user-facing document query is scoped with `{"userId": current_user.id, "isDeleted": False}`.
- Ownership checks return **400** for a malformed id and **404** (never 403) for a valid id that doesn't belong to the current user or is soft-deleted — see `_get_owned_document` in `documents/router.py`. This intentionally avoids leaking whether another user's document exists.
- Session revocation is DB-checked, not JWT-trusted: `auth/dependencies.py:get_current_user` re-reads the user's `tokenVersion` from Mongo on every request and rejects the token if it doesn't match the value baked into the JWT at sign time — this is how forced logout / password-change invalidation works.
- `slowapi` rate limiting (`app/core/rate_limit.py`, per-IP `Limiter`) is currently applied only to `auth` routes (signup/login/etc.), not to `documents`/`admin` routes.

### Frontend
- `frontend/src/pages/DocumentsPage.jsx` — the URL query string (`useSearchParams`) is the source of truth for filters/pagination, mirrored into local `useState`; server data comes through React Query (`hooks/useDocumentsQueries.js` → `api/documents.js`).
- Both `frontend` and `admin` share the same axios-wrapper pattern: `src/api/client.js` sets `baseURL: "/api"`, injects the bearer token, and handles global 401 → logout/redirect.
- Zustand stores exist (`authStore.js`, `dialogStore.js`) but are not used for list/filter state — that stays in the URL + React Query cache.
