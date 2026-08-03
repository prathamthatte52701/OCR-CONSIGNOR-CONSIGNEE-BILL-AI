# THE MAIN OCR

Consignor/Consignee OCR system. FastAPI + Motor (async MongoDB) backend that OCRs uploaded
documents (PaddleOCR / PP-StructureV3) and extracts structured fields via the Groq LLM. Two
separate React/Vite frontends: `frontend/` (end-user app) and `admin/` (admin console).

See `CLAUDE.md` for full architecture notes (pipeline structure, security patterns, commands).

## Known Limitations

- **OCR throughput is single-process and sequential per upload.** Each upload's Part 1 + Part 2
  pipeline runs as a FastAPI background task in the same process serving HTTP requests (no job
  queue/worker pool). PP-StructureV3 table extraction in particular is CPU-heavy (up to 300s for
  an image, 420s for a PDF, vs. 60s/180s for Part 1) and PaddleX threading is pinned to 6 threads
  via `OMP_NUM_THREADS`/`PADDLE_PDX_CPU_NUM_THREADS` (`app/main.py`). Uploading several documents
  back-to-back queues them behind whichever one is currently OCR-ing rather than running in
  parallel — expect noticeably slower turnaround under concurrent uploads.
- **Rate limiting is in-memory, not persistent.** Both the per-IP `slowapi` limiter and the
  per-email login limiter (`app/core/rate_limit.py`) use `limits`' `MemoryStorage`. A backend
  restart or redeploy silently resets everyone's rate-limit counters. This also means rate limits
  only hold within a single process — the app is not set up to run multiple backend workers/
  instances without moving this to a shared store (e.g. Redis). The one exception is the admin
  nuke rate limit (Feature 1), which is Mongo-backed (`auditlogs` query) and does survive
  restarts.
- **Forgot-password has no email verification step.** `POST /auth/forgot-password/verify` and
  `/reset` authorize a reset purely by a username+email match already on file (`auth/router.py`)
  — no reset token, no email actually sent. Anyone who knows both a user's username and email can
  reset that account's password. This is a deliberate design tradeoff already in place, not a
  regression from this work, but worth knowing before treating it as a secure recovery flow.
- **No deployment/production setup exists yet.** There's no Dockerfile, process manager config,
  or multi-worker `uvicorn` invocation anywhere in the repo — the only documented way to run the
  backend is `uvicorn app.main:app --reload`, a single-process dev server. Anything beyond local
  development (containerization, horizontal scaling, a real job queue for OCR) is unbuilt.
- **Download All (bulk ZIP) only covers the current page.** It intentionally does not walk every
  page of a filtered result set — downloading everything requires paging through and running it
  per page.
- **Confidence-based card coloring only applies to documents processed after this feature
  shipped.** `minConfidence` is computed once, at pipeline-completion time, and stored on the
  document; documents processed before this change won't have the field and fall back to the
  neutral/no-data border until reprocessed.
- **GridFS orphaned-file tracking is best-effort and requires manual admin action.** A failed
  file delete is recorded (`orphanedfiles` collection) but nothing retries it automatically — an
  admin has to visit the Orphaned Files page and retry or dismiss each one.
- **Groq LLM extraction is an external dependency with no fallback.** If Groq is unreachable or
  rate-limits the app, the affected document's pipeline run fails outright (`uploadStatus:
  "failed"`) rather than degrading to a partial/manual-entry mode.
