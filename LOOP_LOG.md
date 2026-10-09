# LOOP_LOG

## Start state (git status --short, recorded before any work this run)
```
 M admin/src/App.jsx
 M admin/src/api/admin.js
 M admin/src/components/AdminLayout.jsx
 M admin/src/main.jsx
 M admin/src/pages/AdminLoginPage.jsx
 M admin/src/pages/AdminUsersPage.jsx
 M backend/app/core/test_validators.py
 M backend/app/core/validators.py
 M backend/app/features/admin/router.py
 M backend/app/features/admin/schemas.py
 M backend/app/features/auth/dependencies.py
 M backend/app/features/auth/router.py
 M backend/app/features/ocr/pipeline.py
 M backend/app/main.py
 M backend/app/scripts/seed_admin.py
 M backend/clear_documents.py
 M frontend/src/App.jsx
 M frontend/src/hooks/useAuth.js
 M frontend/src/main.jsx
 M frontend/src/pages/DocumentsPage.jsx
?? LOOP_LOG.md
?? admin/src/components/ErrorBoundary.jsx
?? admin/src/components/PasswordInput.jsx
?? admin/src/pages/AdminForgotPasswordPage.jsx
?? admin/src/pages/AdminProfilePage.jsx
?? backend/app/core/common_passwords.py
?? backend/app/core/test_upload_limit.py
?? backend/app/core/upload_limit.py
?? backend/app/features/auth/test_approval.py
?? backend/app/features/auth/test_approval_logic.py
?? backend/app/features/ocr/page_normalize.py
?? backend/app/features/ocr/test_page_normalize.py
?? backend/app/scripts/migrate_user_status.py
?? frontend/src/components/ErrorBoundary.jsx
?? frontend/src/pages/DocumentsViewAllPage.jsx
```

HEAD: fe9b5e8 Bring project to feature parity with sister Acknowledgement OCR system

Note: several items (approval core, admin approval endpoints/UI, partial password blocklist, upload size middleware, ErrorBoundary, admin profile/forgot pages) were already implemented earlier in this working tree (uncommitted) before this loop started. This loop verifies, completes and hardens them.

## DECISIONS

- D0 (test infra): No local MongoDB/Docker on this machine and the Atlas cluster is unreachable (DNS fails). Rule 2 forbids touching the real DB, so tests run against an in-process fake Mongo (backend/fake_mongo.py) installed by backend/conftest.py. conftest forces MONGO_DB_NAME=docintel_cons_cons_test, aborts the run if the name does not end in _test, and replaces MONGO_URI with a dummy host so a real connection is impossible. If TEST_MONGO_URI is set, conftest uses that real server instead (still _test only) and drops the test DB at session end.

- D1 (new DB): Owner supplied a NEW Atlas cluster (cluster0.wpacri8) and asked to replace the old URI. backend/.env (git-ignored) MONGO_URI replaced; MONGO_DB_NAME stays docintel_cons_cons. Connection test: DNS/SRV resolves but TLS handshake fails (TLSV1_ALERT_INTERNAL_ERROR) - typical of the machine's IP not being in Atlas Network Access. Owner action needed. Until then all tests run on the in-process fake Mongo. The real cluster is only ever used for tests with TEST_MONGO_URI + a *_test database.
- D2 (T1): a status field present but null/garbage/uppercase fails CLOSED (treated as rejected message), only a MISSING field counts as approved.


## TASK LOG

### T0 test infrastructure - GREEN
Files: backend/fake_mongo.py, backend/conftest.py. Whole pre-existing suite (183 tests) passes on the fake. Also fixed 10 pre-existing mypy errors (test_orphaned_files portal typing) so the gate is fully clean.

### T1 Approval core - GREEN (refine rounds: 0)
Files: auth/dependencies.py, auth/router.py, scripts/seed_admin.py, scripts/migrate_user_status.py, auth/test_approval.py (+test_approval_logic.py offline).
Tests added: signup pending, pending/rejected login 403 w/o token, wrong password never reveals status (401), legacy (no status) logs in, old token blocked on protected routes, status flip applies to an existing token, fail-closed for null/garbage/uppercase status (6 params), migration dry-run + idempotent + untouched existing statuses, double signup same email = exactly one user, case-insensitive duplicate email, signup cannot self-assign status/role.
Break tests tried: garbage status values; mass-assignment of status/role at signup (ignored by schema); duplicate signup (generic 400); uppercase email; stale token after flip; migration run 3x.
Decision D2 (fail closed on malformed status) applied.

### T2 Login timing - GREEN (refine rounds: 0)
Files: core/security.py (DUMMY_PASSWORD_HASH, verify_password never raises), auth/router.py (login + change-password no longer KeyError without passwordHash), auth/test_login_timing.py.
Tests: identical status/body unknown vs wrong; spy proves exactly ONE bcrypt check on every failure path (dummy hash for unknown email and for no-password accounts, real hash for wrong password); no-password account = 401 not 500; 73/500-byte, multibyte, NUL passwords = no 500; timing test (unknown not the fast path); verify_password never raises.
Found + fixed while here: bcrypt 5 raises ValueError for >72-byte passwords (would have been a 500 on login) and change-password had the same KeyError on a missing hash.

### T3 Admin approval endpoints - GREEN (refine rounds: 0)
Files: admin/router.py, admin/schemas.py, admin/test_user_approval.py (16 tests, real signed tokens, no dependency overrides).
Break tests: reject admin / self (400, no tokenVersion bump, no audit entry); idempotent approve/reject; anonymous 401 / plain user 403; rejected admin loses admin access immediately; ids: unknown 404, malformed/"123"/"%20" 400; list never leaks passwordHash; status=bogus 422; rejected email cannot re-signup; re-approve then delete.

### T4 User frontend - GREEN (refine rounds: 1)
Files: frontend/src/api/client.js, hooks/useAuth.js, pages/LoginPage.jsx, e2e/helpers.cjs, e2e/test_login_approval.cjs (8 browser checks, backend mocked via page.route).
Behaviour: signup -> login page with "Account created. Waiting for admin approval." banner; login 403 shows the two exact messages inline (role=alert, persistent, no duplicate toast); 401 stays a toast; a user un-approved mid-session is logged out and sent to /login?notice=pending|rejected.
Break tests: notice query param cannot inject free text / markup (fixed key map only); unrelated 403 does not render as an approval banner; message persists 6 s (longer than a toast); 401 never shows the approval banner.
Refine round 1: 2 harness bugs (mock pattern also matched Vite's /src/api/documents.js; init script re-seeded the token on every navigation) - fixed in the tests, not the app.

### T5 Admin panel - GREEN (refine rounds: 0)
Files: admin/src/pages/AdminUsersPage.jsx, admin/src/index.css (success colour), e2e/test_admin_users.cjs (10 checks).
Pending tab + count badge; Approve (instant) / Reject (confirm); Rejected tab: Re-approve (instant) / Delete (critical confirm, permanence warning); Approved: Revoke (confirm); admin rows have no actions.
Break tests: Cancel sends nothing; double-click Approve = exactly ONE request (in-flight guard); button click never navigates to the row link; server error keeps list intact and shows the message.

### T6 Admin access audit - GREEN (refine rounds: 0)
Files: admin/router.py (_log_admin_access; NEW admin routes GET /api/admin/documents/{id}/download/part1|part2), admin UI download buttons (blob, bearer header), admin/test_admin_access_audit.py (10 tests).
Audit entry = userId(adminId), action (admin_viewed_document / admin_downloaded_part1 / _part2), context {targetUserId, documentId}, createdAt. Written BEFORE data is returned: a failing audit write returns 500 and serves nothing (tested).
Decisions: D3 admin file routes did not exist; added them (audited) so "admin sees everything" includes the originals. D6 the admin LIST view is not audited per row (it only shows summaries; one entry per row would flood the log) - only opening a document is. D7 admin opening their OWN document is not logged.
Break tests: failed lookups (400/404) log nothing; purged/missing files serve nothing and log nothing; plain user / anonymous get 403/401 with no data and no entry; entries not deduplicated; owner cannot see admin entries in /me/activity.

### T7 Email admin-only - GREEN (refine rounds: 0)
Files: auth/router.py (PATCH /me), admin/router.py (PATCH /users/{id}: validate, unique, tokenVersion bump, audit previous/new), AdminUserDetailPage (Change email + confirm), ProfilePage (read-only note), auth/test_email_admin_only.py (27 tests), e2e/test_email_admin_only.cjs (6 checks).
Break tests: any DIFFERENT email value (empty, garbage, 300 chars, another user's address) = 403 and NOTHING else is applied (no partial username update); unchanged/uppercase/padded email still allowed; null ignored; admin: duplicate (also case/space variants) 400 with nothing changed, invalid shapes 400, same email = no-op (no logout, no audit), old token revoked + new address logs in, unknown/malformed ids, non-admin 403 incl. on own id.

### T8 Isolation - GREEN (refine rounds: 1)
Files: documents/router.py (isDeleted filter), documents/test_isolation.py (41 tests incl. route x actor matrix), auth/dependencies.py (status checked before tokenVersion).
Every documents route (list, stats, detail, part1, part2, correct, reprocess, purge-files, delete, download-all) + /auth/me/activity: other user -> 404 (never 403) with zero side effects (document snapshot identical, files still downloadable by the owner); collections show only own data (also under filter / regex / injection-style query params); pending, rejected and rejected-via-admin (stale token) users get 403 with the right message on EVERY route and cannot upload; anonymous 401; admin reaches all through /api/admin/* (audited) but user routes stay owner-scoped for admins too.
FINDING (soft-deleted docs): _get_owned_document / list / stats / download-all had NO isDeleted filter - a leftover isDeleted=true document still resurfaced for its owner. Fixed: isDeleted != true on all four. Delete itself is permanent (soft delete no longer exists); CLAUDE.md still describes the old behaviour (updated in T14).
Decision D8: status is now checked BEFORE tokenVersion so a rejected user's old token answers 403 "not approved" (spec wording) instead of 401; token signature is verified first so nothing leaks.
Refine round 1: legacy-soft-delete test failed -> fixed in router.

### T9 Password rules - GREEN (refine rounds: 0)
Files: core/validators.py (password_problem, byte length, control chars, personal info), core/common_passwords.py (255 entries + leet spellings), auth/router.py (signup/change/reset use password_problem), core/test_password_rules.py (37), auth/test_password_rules_api.py (39), test_validators.py updated.
Rules: 8..64 BYTES (multi-byte tested at the boundary: 64-byte password with 34 chars passes, 66-byte fails; proves bcrypt never truncates), upper+lower+digit+special, no whitespace/control chars (NUL would crash bcrypt), blocklist after lowercase + strip trailing digits/symbols, rejects passwords containing username or email local part. New passwords only: legacy weak/long passwords still log in (tested).
Decisions: D4 the "contains username/email" rule ignores parts shorter than 3 chars (a 2-letter local part would otherwise ban half of all passwords). D5 lone surrogates / NUL are rejected with 400 (they used to be possible 500s).
Break tests: lone surrogate, NUL, \t \n \x7f NBSP, emoji (4-byte) boundary, 65/500-byte, reset gives the SAME error whether or not the account exists (no oracle).

### T10 Field limits + upload size - GREEN (refine rounds: 2)
Files: auth/schemas.py (max lengths: username 32, email 254, password 128), admin/schemas.py, documents/schemas.py (CorrectRequest field 64 / value 2000), core/upload_limit.py (custom detail, PATCH, negative/garbage Content-Length), main.py (16 KB cap on every auth route + 422 handler), documents/router.py (_read_capped for BOTH parts, sanitised names), core/filenames.py, admin/router.py (safe download header), frontend/admin download buttons. Tests: core/test_filenames (27), auth/test_field_limits (36), documents/test_upload_limits (25), core/test_upload_limit (+13 ASGI-level).
Upload: declared Content-Length over 2 x 5 MB + 1 MB framing is refused 413 WITHOUT reading a byte or calling the app (probe test: receive_calls == 0 and app_calls == 0); a chunked body with no Content-Length is cut off at the limit; each file is capped while read in 64 KB chunks (exactly 5 MB passes, +1 byte fails, Part 1 checked before Part 2 is read, nothing - no document, no GridFS file - is stored on any rejection); existing empty/type checks unchanged; a "shell.jpg" that is not a JPEG is rejected by content.
REAL BUGS FOUND AND FIXED while breaking it:
 1. The 422 handler echoed pydantic's `input` - a too-long password came straight back in the response body, and a value that cannot be UTF-8 encoded (lone surrogate in JSON) turned the handler itself into a 500. Now only loc/msg/type are returned.
 2. Content-Disposition used the raw uploaded filename: a quote/CR/LF corrupts the header and a non-latin-1 name (e.g. Hindi) made the download a 500. Names are now ASCII, path-free, quote-free (at upload AND at download, so legacy rows are safe too).
 3. Zip slip: download-all used the OCR'd invoice number and the uploaded filename as zip entry names ("../../x"). Now sanitised; every entry is exactly folder/file.
 4. User-facing Part 1 / Part 2 download links were plain <a href> (no bearer token -> always 401). Replaced by authenticated blob downloads (browser-tested: Authorization header sent, filename honoured, server error message shown).
Refine rounds: surrogate payload test (httpx cannot even send it - switched to raw bytes), truncated test file rewritten.

### T11 Login limiter proof - GREEN (refine rounds: 0)
File: auth/test_login_limiter.py (9 tests). Limiter code NOT changed.
21st attempt within 15 min = 429 (attempts 1-20 are normal 401s); a different email and a made-up email are unaffected; the correct password cannot bypass a spent budget; case/space variants share ONE budget; blocked attempts do zero bcrypt work; blocked unknown email == blocked real email (no oracle); budget returns after the window (time patched); 60 concurrent threads -> exactly 20 allowed; a guard test pins the 20 / 15-minute constants.

### T12 Restart recovery - GREEN (refine rounds: 0)
Files: documents/recovery.py (new), main.py (lifespan background task, cancelled on shutdown), core/config.py (RECOVER_INTERRUPTED_UPLOADS, default on), documents/router.py (recoveryAttempts 0 on upload and on reprocess), conftest.py (recovery OFF in tests unless a test asks), documents/test_recovery.py (24 tests, mocked OCR via the `process` seam, tiny synthetic GridFS files).
Behaviour: on startup a background task (never awaited by startup) finds uploadStatus "processing" documents, oldest first, ONE AT A TIME; each attempt is counted in recoveryAttempts BEFORE processing (a hard crash still counts); attempts >= 2 -> status "failed" with a clear processingError + audit entry (no OCR run); purged/missing/dangling GridFS files -> failed + audit; a raising document does not stop the others; cancelled cleanly at shutdown; recovery errors are logged and never affect startup.
Proofs: stuck doc processed from the stored bytes with the right mime types; attempts already 1 in the DB while OCR runs; simulated 5 boots of a document that kills the process: retry, retry, then failed, then ignored (bounded loop); max in-flight OCR = 1; startup < 5 s and /health < 1 s while a recovery sleeps 30 s, shutdown cancels it; crashing recovery does not break startup; switch-off flag works; end-to-end startup requeues a stuck document; reprocess resets the budget.
NOT tested (by design, rule 3): real OCR on a real stuck document - listed for the owner in the report.

### T13 Keyboard shortcuts - GREEN (refine rounds: 2)
Files: frontend/src/components/GlobalConfirmDialog.jsx, admin/src/components/ConfirmModal.jsx (Enter confirms, Esc cancels, busy prop, double-confirm guard, focus on the dialog), frontend/src/components/EditableField.jsx (same-tick double-Enter guard), frontend/e2e/test_shortcuts.cjs (17 checks, results array + SUMMARY line), e2e/helpers.cjs.
Rules implemented: Enter confirms only when focus is NOT on a button/link/field (so Enter on Cancel still cancels, a phrase input still submits normally), never while busy, never on key auto-repeat, never while an IME composes; the dialog takes focus on open (showModal used to focus Cancel, where Enter would cancel). Escape = native <dialog> cancel. NukeDialog untouched: it has no form and no key handler, so Enter cannot confirm it (tested in every field, on the select, on the dialog body); Escape closes it; an explicit click on the red button still works once.
Break tests: two quick Enters = 1 request; held Enter (auto-repeat) = 1 request; three keydowns in the SAME tick on an editable field = 1 PATCH; Enter in filter inputs updates the URL + request; mouse Cancel/Confirm still work.
REAL BUG FOUND: EditableField sent TWO PATCH requests on a quick double Enter (the `saving` state is stale inside the same render closure). Fixed with a ref guard (+ IME / repeat ignored).
Note: the Dashboard has no filter inputs (only Documents does), and the admin Logs filter applies live on every keystroke, so neither needed an Enter handler.

### T14 Cleanup - GREEN with one gap (refine rounds: 1)
- PyJWT: BEFORE the swap a token was minted with python-jose (test-only secret) and saved as backend/app/core/test_fixtures/jose_tokens.json; core/security.py now uses PyJWT 2.15.1 (HS256 pinned, exp required, same claims, same 7-day TTL). core/test_jwt_pyjwt.py (23): the old jose token still decodes, expired old token rejected, new tokens have the identical header/claim set, alg none / HS384 / HS512 / tampered / stripped-signature / wrong-secret / no-exp / garbage all return None. python-jose and its orphans (ecdsa, rsa, pyasn1) uninstalled from the venv; pip check clean.
- /docs, /redoc, /openapi.json: off unless ENABLE_DOCS=true in EVERY environment (they used to be on whenever NODE_ENV != production). core/test_docs_flag.py (9, fresh-interpreter checks).
- seed_admin: already fully env-driven (ADMIN_1_* / ADMIN_2_*); no hardcoded admin name or email exists anywhere in the repo (grep). CLAUDE.md now documents the env vars and every feature of this loop; its stale statements (soft-delete, "not a git repo") were corrected.
- requirements: requirements.txt rebuilt from the working venv (117 exact pins) and requirements-dev.txt (15 pins + -r requirements.txt: ruff, black, isort, mypy, pytest, pytest-asyncio and the packages only they need). No extra-index-url line existed, so none to keep. `pip install --dry-run` of both resolves with nothing to install; pip check clean.
  Found: the OLD requirements.txt was missing the paddlex "ocr" extras that PP-StructureV3 needs (beautifulsoup4, einops, ftfy, latex2mathml, lxml, openpyxl, premailer, scikit-learn, scipy, sentencepiece, tiktoken, tokenizers, ...) - a fresh install would have broken Part 2. They are pinned now (they are in the working venv).
  Excluded on purpose: `playwright` (+ pyee, greenlet) - installed in this venv, imported by nothing in the app or any paddlex extra.
  Possibly unused (not removed, not mine to decide): passlib, sentry-sdk, reportlab.
- npm audit fix (never --force): frontend high 5 -> 0, admin high 5 -> 0 (total 5 -> 0 each); both builds pass, lint 0 errors.
GAP: no single full backend run was done AFTER the dependency swap/pin work (the last full run was 546 passed, then test_docs_flag's 9 passed on their own; 555 collected). The owner asked to pause testing at this point.

## CONSOLIDATED DECISIONS (the D-numbers used inline above were provisional; this is the final list)
1. Test infra: in-process fake Mongo + _test guard (no local mongod / Docker, Atlas was unreachable); TEST_MONGO_URI switches to a real *_test database.
2. New Atlas cluster URI put in backend/.env (git-ignored); DB renamed docintel_transport -> docintel_cons_cons (owner: everything is "cons cons", nothing is "transport"); test DB docintel_cons_cons_test.
3. A status field that is present but null/garbage/uppercase fails CLOSED; only a MISSING field counts as approved.
4. Added admin file download routes (part1/part2) so "admin sees everything" includes originals - audited.
5. Admin LIST view is not audited per row; admin opening their OWN document is not logged.
6. Status is checked before tokenVersion, so a rejected user's old token answers 403 (spec) instead of 401.
7. isDeleted != true filter added to owner-scoped queries (legacy soft-deleted rows must not resurface).
8. Personal-info password rule ignores username/email-local parts shorter than 3 characters.
9. Lone surrogates / NUL in passwords -> 400 (were potential 500s); 422 handler no longer echoes inputs.
10. Filenames/zip names sanitised (header injection, non-latin-1 crash, zip slip); user downloads moved to authenticated blob downloads.
11. migrate() takes an optional db handle (needed so a test can run it on its own event loop).
12. playwright excluded from requirements; paddlex ocr extras added to requirements.
13. Mid-session un-approval sends the user to /login?notice=pending|rejected (fixed keys only).
14. DB wipe / permanent data deletion was NOT performed by the assistant (prohibited action); the owner ran clear_documents.py himself earlier.

<!-- END -->
