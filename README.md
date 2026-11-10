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
| `APP_HOSTS` | Comma-separated allowed HTTP hosts. Default `localhost,127.0.0.1,[::1]`. Add an exact public hostname only when intentionally deploying payment pages. |

`.env` loads on the server only; existing process environment values win. No secret belongs in a `VITE_` variable. `/api/health` reports readiness booleans/model/timezone, never keys. The public config exposes only sandbox readiness and the public client ID.

### Gemini

Create a key through Google AI Studio with access to the configured model. Preserve `gemini-3.5-flash-lite` unless a real API call proves it unavailable; choose any alternate model yourself from your account's actual available models, then set `GEMINI_MODEL`. An unavailable model yields an explicit error; the app does not guess replacements.

```sh
.venv/bin/python test_ai.py
```

First save a **Freelancer display name** in an unpaid request's AI panel. The name is a single-workspace setting stored in SQLite, not an environment variable or hardcoded identity. Restart Flask after upgrading so its additive schema initialization creates `workspace_settings` without replacing requests or payment attempts. A missing name prompts you to add it and blocks AI generation; unsaved name edits must be saved first. Names are trimmed, limited to 120 characters, and must be a single line without control characters. Clearing and saving the name disables generation again. Changing the setting applies to new messages, not existing drafts.

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
2. Open the saved details, enter your **Freelancer display name**, and select **Save display name** if not already configured. Select **Generate payment message**. A successful response is labelled **Real Gemini output** and shows the configured model; its closing uses the saved name. Edit it and use **Copy message**; copy the payment URL separately. Nothing is sent.
3. Open **Open client page**. Check the amount and sandbox warning. Pay as the separate sandbox buyer.
4. Wait for **Payment confirmed**, then return to details/dashboard. The dashboard refreshes when the tab regains focus; **Refresh status** is also available. Confirm paid increased and outstanding decreased; refresh the browser to demonstrate persistence.
5. If checkout is cancelled, the request stays unpaid. If capture is uncertain, use **Check payment status** before trying to pay again. This also works after refreshing the client page when an active order is stored.

See [the under-three-minute demo script](docs/DEMO.md) and [submission checklist](docs/SUBMISSION_CHECKLIST.md).

## Verification

```sh
npm run lint
npm run build
.venv/bin/python -m pytest
npx playwright install chromium
npm run test:browser
```

Linux may need `npx playwright install-deps chromium` (administrator approval/system packages required). Browser checks start their own non-debug Flask server on port 5001, use an isolated ignored database and **blank integration keys**, and check the built application at 375/768/1440px, WCAG A/AA with axe, navigation, validation, persistence, copying, and missing-configuration states. One intercepted AI fixture is visibly labelled **not real AI output**. Screenshots/traces go to ignored `test-results/`. Tests never contact PayPal or Gemini. Backend tests mock external APIs, including the HTTP transport. See [verification notes](docs/VERIFICATION.md) for actual results and unverified checks.

`npm audit` currently reports four moderate **development-tooling** advisories through ESLint's minimatch dependency. No production dependency vulnerabilities were reported. No forced dependency downgrade was applied; do not run `npm audit fix --force` blindly.

## Architecture and API

- `src/App.jsx`, `src/App.css`, `src/index.css`: dashboard, searchable/filterable list, create/details, minimal token payment page. No chatbot, charts, or autonomous sending.
- `backend/config.py`, `db.py`, `models.py`: Flask configuration, SQLite initialization, request validation/serialization.
- `backend/routes.py`, `ai.py`, `paypal.py`, `payments.py`: JSON routes, Gemini adapter, sandbox REST adapter, persisted payment state machine.
- `tests/`: focused mocked backend tests. `browser-tests/`: real Chromium checks of the local app, not live integrations.

Management (local only): `GET /api/health`, `GET/POST /api/requests`, `GET /api/requests/:id`, `GET /api/dashboard`, `POST /api/requests/:id/message`, `GET/PUT /api/settings`. Settings use `{"freelancer_display_name":"Your chosen display name"}`; an empty string clears the name. The name is not added to public payment-page responses.

Public: `GET /api/public/config`, `GET /api/public/requests/:token`, and `POST /api/public/requests/:token/orders`, `/capture` (`{"order_id":"…"}`), `/cancel` (same body). JSON errors consistently use `{"error":{"code":"…","message":"…"}}`.

Amounts enter the API as decimal **strings**, e.g. `"50.10"`, and are stored as integer cents. No binary floating-point money calculations occur on the backend. Due dates are date-only `YYYY-MM-DD`, inclusive through that date in **Africa/Nairobi (UTC+3)**. Overdue means unpaid with a due date before today's Nairobi calendar date. Audit/payment timestamps are stored as UTC ISO 8601; UI payment timestamps are displayed in Nairobi. Outstanding includes overdue; paid requests are excluded from both.

### Payment correctness and recovery

The server reads amount/currency/request ownership from SQLite and creates an opaque 256-bit payment-page token. It persists the attempt and separate UUID idempotency keys **before** network operations, then saves returned order/capture identifiers. It checks order ID, request reference, attempt custom ID, seller merchant ID, USD currency, gross amount, and completed capture status before atomically updating the attempt and request to paid. Duplicate callbacks return the saved result. Cancellation is advisory only, not proof PayPal cannot capture.

SQLite immediate transactions serialize payment operations, including bounded upstream calls, to prevent concurrent double capture/new attempts in this small workspace. This intentionally favors correctness over throughput; a busy workspace can return a retryable database error. An ambiguous create reuses its persisted create key. Every capture attempt first retrieves and verifies the PayPal order; if already captured it records the verified result without another capture. Pending captures block a second payment. Only after successful reconciliation showing an approved, uncaptured order can the same capture key be used again. No HTTP POST is blindly retried.

Automatic retry is blocked after five hours, short of Orders v2's default six-hour idempotency retention. Older uncertain attempts require seller inspection of order/capture history in the sandbox dashboard. Do not delete the database or hand-mark a request paid to bypass this protection. This MVP has no administrative reconciliation editor; investigate the order before any manual database repair and take a backup.

## Security boundaries and limitations

- No authentication, tenant isolation, email, subscriptions, conversion, refund flow, webhooks, or background reconciliation. **Never use real client information or publicly publish the management app.**
- Management API/pages require a loopback peer **and a localhost/loopback Host**, and reject forwarded requests. Public tokens are bearer links: anyone possessing one can see the service/amount/due date and initiate sandbox checkout; protect them. Client names and internal diagnostics are omitted publicly. There is no token expiry/revocation UI.
- No live-service fallback: Gemini/network/model errors remain errors; no fabricated output. Configured readiness is not a live connectivity test.
- Immediate server-side verification supports the demo. If the browser disappears after approval, someone must reopen the token page and check status. Without webhooks/background jobs, later pending completion, refunds, reversals, and disputes will not automatically reconcile. No rate limiting; do not expose APIs without adding abuse controls.
- SQLite serializes writes; this is one workspace, one persistent host, not a distributed/multi-user service. Edited messages are not saved. There is no request editing/deletion in this MVP.

## Local production build and deployment path

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
