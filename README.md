# Freelance Flow

A small AI payment companion for freelancers: save a USD payment request, draft a thoughtful Gemini message, review/copy it yourself, and share a PayPal **sandbox** payment page. Requests become paid only after Flask verifies a completed capture. Built for the PayPal AI Hackathon, due **November 12, 2026, 11:00 p.m. Africa/Nairobi**.

**Single workspace, local management, fictional information only.** There is no login or multi-user authorization. This is not a secure production invoicing service. Nothing is emailed, sent automatically, or charged in production.

## Quick start

Requirements: Python 3.11+ with `venv`, Node.js 22.12+ (or compatible newer Node), npm, and internet for the integrations. Verified environment: Python 3.14.5, Node 25.9.0, Linux.

From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci
cp .env.example .env
```

Edit `.env` locally; never paste credentials into chat or commit them. You can create/save requests without integration credentials. Missing credentials produce explicit recoverable errors, not invented AI responses or paid records.

Terminal 1 (backend, no debugger):

```sh
. .venv/bin/activate
python -m flask --app backend:create_app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

Terminal 2:

```sh
npm run dev
```

Open **http://localhost:5173**, matching `PUBLIC_BASE_URL`. Vite forwards `/api` to Flask on port 5000; no permissive CORS is enabled. SQLite initializes automatically at `instance/freelance-flow.sqlite3`. Refreshing or restarting the app preserves requests and attempts. Restart Flask after changing configuration. Do not set `FLASK_DEBUG=1` for deployment.

To use the **existing Neon PostgreSQL project** instead, follow [Neon setup and verification](docs/NEON.md). Flask uses synchronous Psycopg 3 through a server-only `DATABASE_URL`; React still calls Flask. SQLite remains available and is not automatically copied to or replaced by Neon. Genuine Neon connection, Flask restart, settings, archive and timeline persistence checks passed; details and limitations are recorded in that guide.

Optional fictional seed (only inserts if the database is empty):

```sh
.venv/bin/python -m flask --app backend:create_app seed-demo
```

It creates three **unpaid** requests, never fake AI output or successful payments.

## Environment

| Variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Server-side Gemini key; takes precedence over `GEMINI_API_KEY` when nonblank. |
| `GEMINI_API_KEY` | Alternative Gemini key. |
| `GEMINI_MODEL` | Defaults to existing `gemini-3.5-flash-lite`. No automatic model replacement. |
| `PAYPAL_CLIENT_ID` | Sandbox REST app client ID. Only this credential is exposed to the PayPal React SDK. |
| `PAYPAL_CLIENT_SECRET` | Sandbox seller app secret; server only. |
| `PAYPAL_MERCHANT_ID` | Sandbox **business seller merchant ID**, required to verify the recipient. Not a client ID or buyer ID. |
| `PUBLIC_BASE_URL` | Browser-facing origin for payment links and public mutation Origin. Local management also accepts its own validated localhost origin. Default `http://localhost:5173`; no trailing slash. |
| `DATABASE_PATH` | SQLite filename; relative paths resolve from repository root. Default `instance/freelance-flow.sqlite3`. |
| `DATABASE_URL` | Server-only PostgreSQL URI; takes precedence over `DATABASE_PATH` when nonblank. Blank selects SQLite. Never use a `VITE_` prefix. |
| `FF_ENV_FILE` | Set in the launching shell to select an environment file explicitly, relative to repository root or absolute. Default `.env`; use `.env.local` for Neon. Set `FLASK_SKIP_DOTENV=1` with Flask CLI to prevent its separate automatic dotenv loading. |
| `APP_HOSTS` | Comma-separated allowed HTTP hosts. Default `localhost,127.0.0.1,[::1]`. Add an exact public hostname only when intentionally deploying payment pages. |

The backend explicitly loads the selected environment file; existing process environment values win. No secret belongs in a `VITE_` variable. `/api/health` reports readiness booleans/model/timezone, never keys. The public config exposes only sandbox readiness and the public client ID.

### Gemini

Create a key through Google AI Studio with access to the configured model. Preserve `gemini-3.5-flash-lite` unless a real API call proves it unavailable; choose any alternate model yourself from your account's actual available models, then set `GEMINI_MODEL`. An unavailable model yields an explicit error; the app does not guess replacements.

```sh
.venv/bin/python test_ai.py
```

First save a **Freelancer display name** in a request's AI panel. Once configured, the compact **Sending as … · Edit** summary replaces the setup form. **Edit** opens the field; **Save** persists the name and **Cancel** restores the saved value. The name is a single-workspace setting stored in SQLite, not an environment variable or hardcoded identity. A missing name blocks generation; pending name changes must be saved or cancelled first. Names are trimmed, limited to 120 characters, and must be a single line without control characters. Clearing and saving the name disables generation again. Changing the setting applies to new messages and never rewrites the current draft.

The smoke command above is a **live**, noninteractive test using fictional request facts and your saved display name from the same `DATABASE_PATH` as the app. It prints real output only after a successful Gemini response and exits nonzero when blocked/failed. Request handling uses a reusable service, 12-second per-attempt HTTP timeout and at most two attempts. No raw prompts, keys, or upstream exception bodies are logged. Gemini receives separate `client_name` (recipient from the saved request) and `freelancer_display_name` (sender from workspace settings) facts and is asked for body-only text. The server adds `Hello <saved client name>,` and appends `Kind regards,` followed by the saved freelancer name, defensively removing conventional model-supplied greetings/sign-offs. If the client name is missing or blank, the greeting is exactly `Hello,`—the freelancer's name is never substituted. The UI shows the greeting recipient separately from the editable sender-name setting. Human review is still essential: generated body text is not guaranteed factually correct. Paid requests cannot generate unnecessary reminders. Generated messages appear in an editable textarea; **Copy message** copies its current edited value and **Clear draft** clears the message and source label after confirmation. Edited drafts are tab-local and not persisted; the display-name setting persists across refreshes and restarts.

### PayPal sandbox seller and buyer

1. Sign in to the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/). Under **Testing Tools → Sandbox Accounts**, create/use a **Business** seller and a separate **Personal** buyer. Prefer USD accounts for this USD-only demo.
2. Under **Apps & Credentials → Sandbox**, create/select a REST app tied to that business seller. Put its client ID and secret in the server `.env`.
3. Obtain that same sandbox seller's **merchant ID** from its sandbox account profile/business information (sign into `sandbox.paypal.com` with the sandbox business credentials if needed). Set `PAYPAL_MERCHANT_ID`. Verify the seller belongs to the REST app; a mismatched seller is deliberately rejected.
4. Note the **Personal sandbox buyer's** login from the developer dashboard. Do not use the seller login to buy, or your real PayPal credentials. Keep passwords private.
5. Restart Flask. `/api/health` should report `paypal_configured: true`. This means configured, **not** authenticated/verified live.
6. Open a request's client page, select PayPal, log in as the sandbox buyer and approve. Keep the local servers running until capture verification completes.

The integration uses the current official [React SDK v6 reference](https://developer.paypal.com/sdk/react/reference), [Orders v2](https://developer.paypal.com/api/orders/v2), [OAuth](https://developer.paypal.com/api/rest/authentication), and [idempotency guidance](https://developer.paypal.com/api/rest/reference/idempotency). REST calls are permanently restricted to `https://api-m.sandbox.paypal.com`; the frontend SDK environment is explicitly sandbox. SDK approval triggers backend capture, **not** a browser-driven paid-state update.

For the verified stale-order pre-login failure, safe response diagnostics, and exact fresh-order retry steps, see [PayPal checkout diagnosis](docs/PAYPAL_CHECKOUT_DEBUG.md). Cached orders are retrieved and verified before reuse; only definitively missing/voided orders with no capture started can be replaced.

## Reproduce the end-to-end demo

1. Create `Alex Demo`, `Fictional website design`, `50.00`, with a due date today or in the future.
2. Open the saved details and review **Explain this payment**: concise canonical facts with a readable due date, and a separated **Next step**. Add your freelancer name if missing, or use **Sending as … · Edit** to change it. Select **Generate payment message**. The result is labelled **AI-assisted draft**: internally, Gemini selects a validated wording choice and the app adds payment facts, the saved client greeting and your signature. Edit and **Copy message**; **Copy link** copies the complete payment URL separately. Nothing is sent automatically.
3. Open **Open client page**. Check the amount and sandbox warning. Pay as the separate sandbox buyer.
4. Wait for **Payment confirmed**. Review its sandbox label, service, amount, freelancer name, confirmed time and capture reference. **Print confirmation** opens browser printing; turn off browser Headers and footers to omit the private page URL. Return to details/dashboard, refresh, inspect the recorded activity and persistent totals, then generate a thank-you rather than another reminder.
5. If checkout is cancelled, the request stays unpaid. If capture is uncertain, use **Check payment status** before trying to pay again. This also works after refreshing the client page when an active order is stored.

See [the under-three-minute demo script](docs/DEMO.md) and [submission checklist](docs/SUBMISSION_CHECKLIST.md).

## Verification

```sh
npm run lint
npm run build
.venv/bin/python -m pytest
node --test tests/paymentPresentation.test.js
npx playwright install chromium
npm run test:browser
```

Linux may need `npx playwright install-deps chromium` (administrator approval/system packages required). Browser checks start an isolated test-only Flask process on port 5001 with an ignored database and **blank real integration keys**. Mock providers exercise guidance, errors/retries, cancellation/capture, persisted activity, confirmation and printing; fixture drafts are visibly labelled **not real AI output**. Tests also cover 375/768/1440px layouts, axe accessibility, keyboard navigation, editing/copying and unconfigured states. Screenshots/PDFs/traces go to ignored `test-results/`. These regressions never contact PayPal or Gemini. See [enhancement verification and manual checks](docs/ENHANCEMENTS.md) for the separate genuine Gemini/running-workspace checks and their limitations.

`npm audit` currently reports four moderate **development-tooling** advisories through ESLint's minimatch dependency. No production dependency vulnerabilities were reported. No forced dependency downgrade was applied; do not run `npm audit fix --force` blindly.

## Architecture and API

- `src/App.jsx`, `src/App.css`, `src/index.css`: dashboard, searchable/filterable list, create/details, minimal token payment page. No chatbot, charts, or autonomous sending.
- Typography uses self-hosted Inter (`@fontsource/inter`, normal Latin 400/500/600/700, swap loading) with system sans-serif fallback. Shared type-scale tokens live in `src/index.css`; form controls, the Clear draft dialog and print confirmation inherit the same font. Browser checks verify rendered fonts, long-content reflow and native Chromium 200% zoom using an isolated test-only extension, never the user's browser profile.
- Request-details presentation is centralized in `src/paymentPresentation.js`; it formats dates/amounts but uses the backend's canonical payment status, timing, overdue-day count and attempt outcome unchanged. The existing React Router dependency's data-router provider enables `useBlocker` for edited-draft navigation protection without changing route paths or adding a dependency.
- `backend/config.py`, `db.py`, `models.py`: explicit environment configuration, SQLite/PostgreSQL initialization and migrations, request validation/serialization.
- `backend/routes.py`, `ai.py`, `paypal.py`, `payments.py`: JSON routes, Gemini adapter, sandbox REST adapter, persisted payment state machine.
- `tests/`: focused mocked backend tests. `browser-tests/`: real Chromium checks of the local app, not live integrations.

Management (local only): `GET /api/health`, `GET/POST /api/requests`, `GET /api/requests/:id`, `GET /api/dashboard`, `POST /api/requests/:id/message`, `GET/PUT /api/settings`. Details include factual guidance, recorded activity and verified confirmation when available. Message generation accepts `{"context_aware":true}` for safe AI-assisted wording (including paid thank-yous); the legacy message behavior is retained for compatibility. Settings use `{"freelancer_display_name":"Your chosen display name"}`; an empty string clears the name. The display name is exposed publicly only inside a verified paid confirmation; client identity and settings endpoints remain private.

### Archive old demo requests

Open request details → **Archive request** → confirm in the in-app dialog. Archive is reversible: it hides the request from the default dashboard, list, recent requests and all totals, which explicitly exclude archived requests. Choose **Archived** in the request-list filter, open the request and select **Restore request** to bring it back. Payment status remains Paid/Pending/Overdue independently of archive state. No request, order, capture reference or timeline entry is deleted, and restoring never creates or captures a payment.

Management-only APIs: `POST /api/requests/:id/archive`, `POST /api/requests/:id/restore`, and `GET /api/requests?archived=1` (default `archived=0` lists active requests). Archive uses the same SQLite write lock as payment operations and rejects creating, capturing, uncertain or inconsistent local attempts. A saved, unstarted order must be retrieved with the configured app and verified against the request's amount/currency/payee/binding. Only an unapproved `CREATED`, verified `VOIDED`, or authoritative missing order with no capture started can be archived; approved/payer-action/pending/completed-but-unreconciled orders and lookup/authentication errors block archiving. Archive never sends an order/capture POST or silently reconciles payment state.

Archived unpaid token links return **“This payment request is no longer available.”** Their details/create/capture/cancel endpoints are blocked server-side, including callbacks from a popup opened before archive. Existing verified paid confirmations remain accessible through their original token and printable. Unpaid reminders are disabled until restore; paid thank-you drafts remain available. Archive/restore are not public endpoints. The timeline remains unchanged by these visibility actions.

**Restart all backend processes before using archive**, then refresh the browser. Startup transactionally adds the nullable `archived_at` column and an index if missing. Existing records default to active; no data reset, seeding or manual SQL is needed. Do not use archive to bypass uncertain-payment reconciliation.

Public: `GET /api/public/config`, `GET /api/public/requests/:token`, and `POST /api/public/requests/:token/orders`, `/capture` (`{"order_id":"…"}`), `/cancel` (same body). JSON errors consistently use `{"error":{"code":"…","message":"…"}}`.

Amounts enter the API as decimal **strings**, e.g. `"50.10"`, and are stored as integer cents. No binary floating-point money calculations occur on the backend. Due dates are date-only `YYYY-MM-DD`, inclusive through that date in **Africa/Nairobi (UTC+3)**. Overdue means unpaid with a due date before today's Nairobi calendar date. Audit/payment timestamps are stored as UTC ISO 8601; UI payment timestamps are displayed in Nairobi. Outstanding includes overdue; paid requests are excluded from both.

Message edits are tab-local, not persisted or automatically sent. Internal navigation to another page (including Back/Forward) prompts **Leave this draft?** only for meaningful edits; Keep editing, Escape and the backdrop retain them. Untouched generated drafts, reverted edits, whitespace-only text and intentionally cleared drafts do not trigger that prompt. Copying is not persistence and does not clear the edited state. Refresh/tab-close protection uses the browser's native `beforeunload` warning: its text/appearance is browser-controlled, may require prior user interaction, and cannot reliably be replaced by a custom app dialog. Saving a sender name or cancelling navigation never calls Gemini or alters payment records.

Restart Flask after updating: initialization adds `payment_events` without replacing requests/attempts. Existing records show only history supported by reliable saved timestamps; old order/cancellation events are not invented. Confirmation requires matching persisted completed-capture evidence, never just a URL flag or browser callback. See [enhancement notes, migration/restart and manual checklist](docs/ENHANCEMENTS.md).

### Payment correctness and recovery

The server reads amount/currency/request ownership from SQLite and creates an opaque 256-bit payment-page token. It persists the attempt and separate UUID idempotency keys **before** network operations, then saves returned order/capture identifiers. It checks order ID, request reference, attempt custom ID, seller merchant ID, USD currency, gross amount, and completed capture status before atomically updating the attempt and request to paid. Duplicate callbacks return the saved result. Cancellation is advisory only, not proof PayPal cannot capture.

SQLite immediate transactions serialize payment operations, including bounded upstream calls, to prevent concurrent double capture/new attempts in this small workspace. PostgreSQL uses the same transaction boundaries with a transaction-scoped workspace advisory lock acquired before reading state. This intentionally favors correctness over throughput; a busy workspace can return a retryable database error. An ambiguous create reuses its persisted create key. Every capture attempt first retrieves and verifies the PayPal order; if already captured it records the verified result without another capture. Pending captures block a second payment. Only after successful reconciliation showing an approved, uncaptured order can the same capture key be used again. No HTTP POST is blindly retried.

Automatic retry is blocked after five hours, short of Orders v2's default six-hour idempotency retention. Older uncertain attempts require seller inspection of order/capture history in the sandbox dashboard. Do not delete the database or hand-mark a request paid to bypass this protection. This MVP has no administrative reconciliation editor; investigate the order before any manual database repair and take a backup.

## Security boundaries and limitations

- No authentication, tenant isolation, email, subscriptions, conversion, refund flow, webhooks, or background reconciliation. **Never use real client information or publicly publish the management app.**
- Management API/pages require a loopback peer **and a localhost/loopback Host**, and reject forwarded requests. Public tokens are bearer links: anyone possessing one can see the service/amount/due date and initiate sandbox checkout; protect them. Client names and internal diagnostics are omitted publicly. There is no token expiry/revocation UI.
- No live-service fallback: Gemini/network/model errors remain errors; no fabricated output. Configured readiness is not a live connectivity test.
- Immediate server-side verification supports the demo. If the browser disappears after approval, someone must reopen the token page and check status. Without webhooks/background jobs, later pending completion, refunds, reversals, and disputes will not automatically reconcile. No rate limiting; do not expose APIs without adding abuse controls.
- SQLite serializes writes; this is one workspace, one persistent host, not a distributed/multi-user service. Edited messages are not saved. There is no request editing/deletion in this MVP.

## Local production build and deployment path

The persistent-disk instructions below describe the SQLite option. Neon setup is documented separately in [docs/NEON.md](docs/NEON.md); changing databases does not authorize deployment or remove the local-only management restrictions.

To run the production frontend and backend together locally:

```sh
npm ci
npm run build
. .venv/bin/activate
PUBLIC_BASE_URL=http://localhost:8000 gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 90 'backend:create_app()'
```

Open `http://localhost:8000`. This serves Vite's built assets from Flask, supports direct navigation to requests/token pages, and never enables a debugger.

**Do not deploy automatically.** A realistic approved deployment is a single Linux VM/container with a persistent disk mounted at `/var/lib/freelance-flow`, `DATABASE_PATH=/var/lib/freelance-flow/freelance-flow.sqlite3`, one Gunicorn worker with four threads, server-only secrets, and an HTTPS reverse proxy. Use SQLite's backup API (or stop the app before copying the DB and WAL files together); test restore. Do not use ephemeral/serverless filesystems or multiple machines sharing SQLite. Rebuild/redeploy without replacing the persistent volume. Schema initialization is additive for this initial schema; future changes need explicit migrations.

If public **sandbox client pages** are approved later: set `PUBLIC_BASE_URL=https://payments.example.com`, add the exact hostname alongside the local defaults in `APP_HOSTS`, and expose **only** `/pay/*`, `/assets/*`, and `/api/public/*` at that hostname. Explicitly deny `/`, `/requests*`, `/api/requests*`, `/api/dashboard`, and `/api/health` in the proxy. Preserve the original Host and set `X-Forwarded-For`; management will reject it. Keep management accessed directly via localhost or an SSH localhost port forward, for example `ssh -L 8000:127.0.0.1:8000 user@server`, then open `http://localhost:8000`. Local management accepts its own validated localhost Origin and creates links using the configured public base; public hostnames are deliberately not management hosts. A fully remote shared management service requires authentication/authorization and a reviewed origin/security design first. Keep all payment integration sandbox-only.

## License

[MIT](LICENSE).
