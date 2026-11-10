# PayPal sandbox checkout diagnosis — November 10, 2026

## Identified cause

`create_order()` returned a persisted order ID without retrieving it from PayPal. Request #1's attempt, created November 9, was still locally `created`, but PayPal no longer recognized its order. Repeated application HTTP 201 responses therefore did **not** mean a new PayPal order had been created.

The original order `67C41114071414213` returned sandbox Orders GET **404**, `RESOURCE_NOT_FOUND` / `INVALID_RESOURCE_ID` (debug ID `f4398162bb931`; repeated during the fixed-route check as `f570933a1cd2d`). Its v6 popup reproduced “Things don't appear to be working at the moment” with no buyer login. The exact reason PayPal removed/no longer recognizes that older order is not established; stale-order reuse is established.

## Implementation and official documentation checked

- Installed `@paypal/react-paypal-js` **10.6.1**, importing **`/sdk-v6`**, with `@paypal/paypal-js` **11.3.0**. Browser loaded sandbox `/web-sdk/v6/core` and `/web-sdk/v6.72.0/paypal-payments`; checkout identified `JS_SDK_V6`.
- Current official [React v6 reference](https://developer.paypal.com/sdk/react/reference.md) and [v6 setup](https://developer.paypal.com/sdk/js/set-up.md) confirm `clientId`, `environment="sandbox"`, `components={['paypal-payments']}`, and `createOrder` resolving to **`{ orderId: string }`**. The existing implementation already conforms. A server OAuth access token is not sent to the browser. No SDK changes were made.
- Backend OAuth and Orders requests use only `https://api-m.sandbox.paypal.com`. Checked [Orders v2](https://developer.paypal.com/api/orders/v2.md) and its authoritative [schema](https://developer.paypal.com/api/orders/v2/schema.json), including order states and payee merchant identifiers.
- Running backend's public client ID matched the locally loaded server client ID (compared privately, not printed). Frontend receives that ID from `/api/public/config`, not a separate build-time credential.
- A fresh $1.00 USD application order was created, and GET using the **same server credentials** returned 200, `CREATED`, `CAPTURE`, the expected amount, and a payee merchant ID matching configuration. It included an `approve` link on `www.sandbox.paypal.com/checkoutnow`; no `payer-action` link was present in this `CREATED` response.
- A separate sandbox order created **without an explicit payee** resolved to the same configured merchant. This verifies the configured recipient is the app's default seller, rather than merely echoing an arbitrary requested payee. The authenticated developer dashboard/account profile and explicit Business account-type metadata were not inspected.

## Fix and safety boundaries

- Retrieve and verify cached orders before reusing them.
- Replace only a definitive Orders GET 404 `RESOURCE_NOT_FOUND` / `INVALID_RESOURCE_ID`, or verified `VOIDED` order, when local capture has **never started**. Preserve the old attempt as failed with `order_unavailable`.
- Reuse available `CREATED` / `PAYER_ACTION_REQUIRED` orders. Approved/completed/unknown states require payment-status reconciliation, not another buyer checkout.
- Never create replacements on authentication errors, lookup timeouts, mismatched payment facts, uncertain capture, or pending payment. No time-based blind replacement and no automatic POST retries.
- Persist replacement idempotency keys before contacting PayPal. Concurrent retries select the active attempt under the database write lock and converge on one replacement.
- PayPal error logs allowlist HTTP status, symbolic error name/issues, and validated `debug_id` only. Public application errors expose `debug_id` when available, never upstream bodies, credentials, access tokens, or buyer details.

## Verification: automated versus live

**Automated regressions, mocked external APIs:** 110 backend tests passed, including replacement/mismatch/error/uncertain-capture guards, concurrent replacement, replacement timeout key reuse, committed-before-POST keys, late-error retirement safety, and diagnostic redaction. `npm run lint` and `npm run test:browser` passed; the latter built production assets and ran both Chromium tests including the existing 15 accessibility scans. These browser regression tests use blank integration credentials and do not establish live checkout success.

**Actual live sandbox checks:**

- Real OAuth, order creation and server-side retrieval succeeded. No fixtures were substituted.
- Before the fix, Chromium reproduced the original cached order's pre-login error with application HTTP 201 and `JS_SDK_V6`; no console/network failure explained that response.
- The updated Flask route was exercised through a test client backed by the real configured service/database (not the already-running old Flask process). It retired request #1's missing order and returned actual replacement **`23H44736Y20200641`**. Same-app GET returned 200, `CREATED`, **USD 1.00**, matching merchant, and sandbox approval URL (debug ID **`f63085529a39e`**).
- The existing browser-facing app then opened that replacement on the original request and displayed the buyer email/login field instead of the generic error. Request #1 remains unpaid.
- A fresh diagnostic request #2 also reached buyer login. It remains unpaid. One separate unbound implicit-seller probe order was created solely to verify seller identity; no diagnostic order was approved or captured.
- One initial fresh-order run encountered PayPal telemetry CORS failures at `c.paypal.com` and a Google CSP-report request blocked by Chromium, without blocking login. One later login run recorded an uncaught page error; it did not reproduce on the follow-up run, which reached login with no page errors. The stale-order reproduction had no console/network errors. These observations do not establish that every browser session is error-free.
- **Not verified:** buyer authentication, approval, capture, settlement, and the complete paid-state journey. No buyer credentials were entered. No real-money transaction, account recreation, or SDK version change occurred.

## Exact retry with a fresh order

1. Stop Flask in its existing terminal with Ctrl+C, then restart from the repository root so the fix is loaded:

   ```sh
   .venv/bin/python -m flask --app backend:create_app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
   ```

   Keep `npm run dev` running in the other terminal. No credential changes are needed.
2. Open **http://localhost:5173/requests/new**. Create a new fictional request (for example, “Sandbox retry”, amount **1.00 USD**, a valid future due date). Using a new request guarantees no existing attempt/order is reused. Do not delete old attempts or reset the database.
3. Select **Open client page**. Open browser DevTools → Network and enable Preserve log. Select **Pay with PayPal** once. The application's `/orders` response should be HTTP 201 with a **new** `order_id`, different from the diagnostic IDs above.
4. Confirm the popup is `www.sandbox.paypal.com/checkoutnow` and displays buyer login. Log in privately using the **separate Personal sandbox buyer**, not the Business seller or real PayPal credentials. Approve the $1.00 sandbox payment.
5. Wait for the application `/capture` response and **Payment confirmed**. Refresh the request/dashboard to verify paid status persists. Approval alone is not proof of payment. If the result is uncertain, use **Check payment status**, not a new payment request.
6. If checkout still fails, retain only the order ID, timestamp, application error code, safe PayPal `debug_id` (Network response or backend log), failing host/status, and whether login appeared. Do not share full popup URLs, payment-page tokens, raw HAR files, request headers, OAuth responses, buyer details, or environment values.
