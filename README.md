# THE MAIN OCR

Consignor / Consignee document OCR. Upload a document as a pair of images (or PDFs), get the
fields read, checked and ready to review, edit and download.

- **Part 1** - consignee / consignor header (consignee code, name, GSTIN, PAN, invoice number, date ...).
- **Part 2** - line items (serial no, description, HSN/SAC, basic, quantity, amount) and the tax summary.

Backend: FastAPI + Motor (async MongoDB). OCR: PaddleOCR (Part 1) and PP-StructureV3 tables
(Part 2). Field extraction: Groq LLM. Frontends: two separate React/Vite apps, `frontend/` for
users and `admin/` for the admin console.

`CLAUDE.md` holds the detailed architecture and rules.

## Features

**Users**
- Sign up, wait for admin approval, log in, forgot / change password.
- Upload one document pair or a bulk set (up to 5 pairs at once); 5 MB per file; JPG, PNG or PDF.
- Live processing status, automatic restart recovery for interrupted jobs, reprocess.
- Review page: every field with its confidence, inline correction, side-by-side original image.
- Review warnings computed from the data: implausible date, line items vs Total Basic Amount,
  Total Basic Amount + taxes vs Total Amount, multi-page note, line item serial numbers,
  empty or junk descriptions, quantity x basic vs amount.
- Document list with search, month / date / IST range filters, status and needs-review filters,
  server-side sorting, paging, confidence-coloured cards.
- Download one document or Download All as a ZIP; delete a document or only its files.
- Dashboard with stats and storage use; My Activity log.
- Chat with the admins, with file attachments.

**Admins**
- Dashboard: 14-day upload / failure series, 7-day trends, pending approvals, grouped activity feed.
- Users: approve, reject, revoke, force logout, delete, password-reset requests.
- Documents across all users (every cross-user access is audited), purge files, orphaned file retry.
- Maintenance tools (bulk delete with rate limit and audit), audit log.
- Chat inbox for user messages.

## Project layout

```
backend/    FastAPI app (app/core, app/features/{auth,admin,documents,ocr,chat}), tests next to code
frontend/   user app (Vite + React, React Query, Zustand)
admin/      admin app (Vite + React)
```

## Run locally

Requirements: Python 3.12, Node 20+, a MongoDB instance, Groq API key(s).

```bash
# backend (from the repo root)
python -m venv venv
venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt   # Linux/macOS: venv/bin/pip
cd backend
cp .env.example .env      # or create .env, see the variables below
uvicorn app.main:app --reload --port 9000

# first admin (reads ADMIN_* variables from .env)
python -m app.scripts.seed_admin

# user app, http://localhost:6001
cd frontend && npm install && npm run dev

# admin app, http://localhost:7000
cd admin && npm install && npm run dev
```

### Running behind a proxy

Rate limits are keyed on the connecting IP. Behind a reverse proxy every user would look like the
proxy's address, so let uvicorn rewrite the client address itself, for the trusted proxy only:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 9000 --proxy-headers --forwarded-allow-ips="10.0.0.5"
```

Set `--forwarded-allow-ips` to the proxy's address (comma separated for several), **never `*`**:
with `*` anyone can send a forged `X-Forwarded-For` header and pick their own rate-limit key.
The app never reads `X-Forwarded-For` on its own; a header that no trusted proxy rewrote is
ignored (covered by `app/core/test_rate_limit_key.py`).

### Environment variables (`backend/.env`)

| Variable | Purpose |
|---|---|
| `MONGO_URI`, `MONGO_DB_NAME` | database connection and name (default `docintel_cons_cons`) |
| `GROQ_API_KEYS`, `GROQ_MODEL` | Groq keys (comma separated) and model |
| `JWT_SECRET` | token signing secret |
| `PORT` | backend port (default 9000) |
| `FRONTEND_ORIGIN`, `ADMIN_ORIGIN` | allowed CORS origins |
| `ADMIN_1_EMAIL`, `ADMIN_1_USERNAME`, `ADMIN_1_PASSWORD` | first admin for `seed_admin` |
| `ENABLE_DOCS` | `true` exposes `/docs` |
| `RECOVER_INTERRUPTED_UPLOADS` | re-queue documents stuck in processing at startup |
| `CHAT_FILES_MAX_TOTAL_MB` | chat attachment storage cap (default 75) |

Never commit `.env`.

## Development

From `backend/` with the repo `venv`:

```bash
pytest                      # tests never touch a real database (in-process fake Mongo, *_test DB guard)
pytest path/to/test_file.py # one file
ruff check . && black . && isort . && mypy .
```

From `frontend/` or `admin/`: `npm run dev`, `npm run lint`, `npm run build`.
Small pure-logic tests run with `node --test src/**/*.test.js`.

## Security in brief

- JWT (HS256, 7 days) re-validated against the database on every request; admin approval gate.
- Passwords: 8-64 bytes, mixed case, digit and symbol, common passwords rejected.
- Rate limits on auth routes, upload size limits, sanitised filenames, security headers.
- Every user query is scoped to the owner; another user's document is a 404.
- Admin access to user documents and files is audited before data is returned.
