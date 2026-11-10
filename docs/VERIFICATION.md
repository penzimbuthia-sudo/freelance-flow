# Verification record

**Clear-draft follow-up (November 10):** the old handler called `window.confirm` directly. With that host API unavailable, the failure was reproduced as `TypeError: window.confirm is not a function`. It now uses an in-app, labelled dialog with initial Keep draft focus, keyboard trapping, Escape/backdrop dismissal and focus restoration (textarea after confirmed clearing). Drafts remain tab-local; clearing makes no persistence or Gemini request. **5 Chromium tests**, **155 backend tests**, frontend lint without warnings and production build passed. Focused checks at 375px/1440px verified edits/source preservation on cancel, independent drafts in separate tabs, unchanged payment facts/activity/settings, accessible dialog labels, no native prompts and no console errors. Providers were mocked/intercepted; this fix did not require live Gemini/PayPal calls or a schema migration.

**Enhancement sprint update (November 10):** rebuilt in conventional commits after restoring the pre-enhancement baseline. **155 backend tests**, lint/build, and **3 Chromium tests** pass, including guidance, persisted activity and confirmation/print. Two genuine Gemini UI calls and the existing paid confirmation were verified on a separate local server; existing requests/attempts/settings were unchanged. No new live PayPal capture was attempted. See [full evidence, limitations, migration and manual checklist](ENHANCEMENTS.md). Earlier counts and missing-credentials statements below are historical.

**November 10 update:** the live PayPal pre-login failure was reproduced and its stale-order reuse cause fixed. 110 backend tests, lint, build, and both browser regressions pass. Actual sandbox OAuth/create/GET and popup buyer-login rendering were verified, but buyer authentication/approval/capture were not. See [PayPal diagnosis and exact retry steps](PAYPAL_CHECKOUT_DEBUG.md). The November 9 results below are historical; their missing-credentials limitation no longer describes the PayPal checks above.

This document distinguishes local/mocked checks from live integrations. Checked on November 9, 2026, on Linux with Python 3.14.5 and Node 25.9.0.

## Completed
- Backend: **94 mocked tests passed**, including persistence, decimal precision, totals/overdue, configuration precedence, AI success/error cases, PayPal binding/merchant/amount/currency validation, cancellation, pending/failure, idempotency, concurrent callbacks, uncertain-capture recovery, local/public-origin boundaries, and the name/draft checks below.
- `npm run lint`: passed.
- `npm run build`: passed.
- Initial MVP live Gemini smoke command: run, **blocked** with `ai_not_configured`. Default model was not changed. Live Gemini and PayPal calls were not rerun for the display-name update; their model/configuration/transport and PayPal payment logic were preserved.
- Dependency audit: four moderate ESLint/minimatch **development** advisories; no production vulnerabilities reported. Existing ESLint major version preserved.
- `npm audit --omit=dev`: passed with **0 vulnerabilities** (a transient registry failure on an earlier attempt was resolved on retry).
- `.venv/bin/python -m pip check`: passed, no broken requirements.
- Actual **Gunicorn** startup and built frontend serving: passed on localhost:5000 with an isolated database under `/tmp/opencode`.
- Existing Vite server on localhost:5173: verified the updated UI is served and `/api` proxy works. Starting a second Vite instance correctly failed because the port was already in use; the existing server was preserved.
- Real local HTTP create/read/dashboard/public-details and expected missing-integration error checks: passed. Only fictional startup-verification data was used.
- Ignore rules and tracked-file checks: no tracked environment files, databases, virtual environments, generated artifacts, or recognized key/private-key patterns found. This limited scan is not a formal security audit.
- `npm run test:browser`: **2 Chromium tests passed**, including creation/validation, persistence after refresh, search/status filters, real missing-AI-configuration handling, editable drafts, clipboard copying, token-page minimal details, unconfigured checkout behavior, keyboard skip link/focus, and no unexpected console errors, failed network requests, or HTTP error responses. Intentional validation 400 and missing-configuration 503 responses are asserted and excluded from unexpected errors.
- Responsive checks and screenshots: dashboard, request list, creation form, details, and client page at **375px, 768px, and 1440px**, with no document-width overflow.
- **15 axe WCAG A/AA scans** passed (five views × three widths). This is automated coverage, not a full manual screen-reader audit. Desktop dashboard, mobile details, and tablet client-page screenshots were also visually inspected.
- Browser tests initially found a visually-hidden table heading escaping its scroll container on mobile; adding a positioned scroll container fixed it and the suite was rerun successfully. The multi-size accessibility test was given a 120-second timeout instead of the default 30 seconds.
- A browser-only intercepted AI response is explicitly labelled **test fixture, not real AI output**. It is not an application fallback and proves no live Gemini behavior.

## Display-name and editable-draft update
- Settings API defaults to no name, trims/validates saves, supports name updates/removal, and persists the single workspace setting across a reopened Flask app/SQLite connection. Tests verify it is local-only and not exposed by public request/config endpoints.
- Additive initialization was tested against a database with existing requests and a saved PayPal order but no settings table; those records were preserved.
- AI tests verify the saved name is passed to Gemini, a name supplied in the generation request body cannot override it, an unset name prevents upstream calls, and changing the saved setting changes subsequent closings. Server-appended closings use the saved name; conventional invented model signatures (including inline/Markdown sign-offs) are discarded.
- The expanded Chromium journey verifies the missing-name prompt and disabled generation, saving/updating a name and refreshing to confirm persistence, copying a generated test-fixture message, editing it and copying the exact edited value, cancelling and confirming Clear draft, cleared controls/source/copy feedback, and retention of the saved name after draft clearing. The 15 responsive accessibility scans still pass.

## Client greeting versus freelancer closing regression
- The greeting is constructed from the request's `client_name`; the closing is constructed independently from the workspace's `freelancer_display_name`. The AI prompt explicitly distinguishes recipient and sender and asks Gemini not to supply either greeting or closing. The UI labels the greeting recipient separately from the sender setting.
- Regression cases use **Alex Demo** as the saved client and **Taylor Demo** as the saved freelancer, including model responses that wrongly greet the freelancer or an invented recipient. The resulting greeting/closing use the correct independently saved names, and spoofed names in the generation request body cannot override them.
- Missing, null, empty, and whitespace-only client-name facts all produce exactly `Hello,`, not a freelancer-name fallback. Greeting-only upstream responses remain errors rather than being presented as successful AI messages.
- Reran the full backend suite, frontend lint, production build, both Chromium tests, and 15 accessibility scans successfully. Live Gemini/PayPal calls were not rerun; their transports, credentials, model, and payment logic were unchanged.

## Live checks blocked
No Gemini or PayPal credentials were available in the environment. Therefore **no real Gemini output, PayPal OAuth/order/capture, buyer approval, or complete real-payment journey has been verified**. Mocked tests do not establish live integration success.

Set `GOOGLE_API_KEY` (or `GEMINI_API_KEY`), `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and the matching `PAYPAL_MERCHANT_ID` locally in `.env`, restart Flask, save a freelancer display name in the AI panel, run `test_ai.py`, then follow the README end-to-end demo with the separate sandbox buyer. Never paste secrets into chat.

The actual PayPal SDK popup, buyer login, live capture callbacks, and pending settlement behavior were not exercised in Chromium because sandbox credentials were absent. No real-service AI generation was exercised in Chromium. Public deployment, hackathon submission, and external account changes were not performed.
