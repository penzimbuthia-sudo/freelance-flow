# Payment clarity enhancement sprint

Implemented and checked November 10, 2026. The first enhancement pass was rolled back at the user's request, restoring the 110-test baseline without removing the prior PayPal fix or existing records. The work was then rebuilt in conventional commits:

- `1c9d728` — `fix(paypal)`: isolate the pre-existing cached-order fix.
- `8f732b3` — `feat(guidance)`: context-aware facts and editable AI-assisted messages.
- `ec8c452` — `feat(activity)`: persisted, deduplicated payment activity.
- `69d7dba` — `feat(confirmation)`: verified sandbox confirmation and print view.
- `ca055c4` — `test(e2e)`: isolated mocked-provider browser coverage.
- `331606c` — `fix(confirmation)`: require capture evidence for all success labels.
- `f67855f` — `fix(print)`: keep print page backgrounds white.

## What changed

### Explain this payment

The existing request-details AI panel now shows **What’s happening**, **Recommended next action**, and an editable **Suggested message**. Python reads canonical saved facts, computes calendar-day overdue counts using **Africa/Nairobi**, and distinguishes future due dates, due today, overdue, paid, recorded failed/unavailable orders, browser-reported cancellation, and unresolved attempts. Uncertain payments recommend checking status, never a new payment. Paid guidance offers thanks, never another reminder.

Generation remains a deliberate button click, using the same Gemini client, configured model, 12-second per-attempt timeout, bounded retries, saved freelancer name, and editable/copyable draft. The new path sends only timing, purpose, attempt outcome and overdue-day context. Client-entered names/service text, URLs, capture references and credentials are not needed by the model and are excluded.

**AI-assisted wording selection is explicitly labelled:** Gemini returns a strictly validated JSON wording choice (`warm`, `concise`, or `gentle`). The app composes all factual claims, the greeting from the saved client name, and the signature from the saved freelancer name. This intentionally restricts generative freedom so the model cannot invent amounts, status, dates, promises, fees, payment references, or links. It is not described as free-form AI authorship. There is **no silent fallback** when Gemini fails or returns invalid/empty output. Facts remain visible; retry and manual editing remain available. URLs are copied separately from the existing deterministic payment-link field.

`POST /api/requests/:id/message` accepts `{"context_aware":true}` for this path; the existing legacy message API is retained for compatibility. Requests cannot override saved payment facts or identities. The server rejects guidance if payment facts change during generation. The UI retains—but warns about and blocks copying—an earlier unpaid draft after the request becomes paid, until it is edited or cleared.

### Payment activity

An additive `payment_events` table records request creation, verified order creation, confirmed capture, browser-reported cancellation, recorded failure, and unavailable-order retirement. Events and the corresponding state writes share a transaction. Unique event keys prevent duplicate events on repeated callbacks/retries. Cancellation is advisory, must be bound to the request, and cannot override paid status or overwrite uncertain-capture diagnostics.

Existing records are **not** given invented/backdated order or cancellation events. Their reliable `created_at` can support Request created; a matching completed capture and `paid_at` can support Payment confirmed. Mutable attempt timestamps are not treated as historical proof. The timeline is management-only and exposes fixed labels/timestamps—not public tokens, idempotency keys, raw provider bodies, buyer details, or claims about views/delivery.

### Confirmation and printing

Both request details and the existing opaque-token public page can show a confirmation only when the persisted request is paid, has a capture reference and confirmation timestamp, and has a matching completed payment attempt. Those facts are written by the existing verified capture path. Query parameters, browser approval, and a paid flag without capture evidence cannot produce success labels or a print button.

Confirmation includes the service, gross paid amount/currency, current configured freelancer display name if present, server confirmation time in Nairobi, capture reference, and explicit sandbox/test-payment wording. It does not expose client identity or unrelated records publicly and is **not a tax invoice**. Printing calls `window.print()`; print CSS excludes navigation, buttons, drafts and diagnostics. No new dependency, SDK change, account change, deployment, or repository-visibility change was made.

## Checks actually passed

**Automated regressions — external APIs mocked:**

- **155 backend tests:** original payment/idempotency/cancellation tests, all timing states and calendar-day calculations, greeting/signature separation, paid thank-you wording, malformed/empty/error AI output, saved-fact spoofing, prompt-data minimization, mid-generation status changes, event persistence/deduplication/concurrency, legacy migration, capture evidence, token isolation, and absence of test-only routes in the production app.
- `npm run lint` and `npm run build` passed.
- **3 Chromium tests** passed: generation/edit/clipboard, AI failure/invalid/empty/retry, refresh-persisted events, mocked approval/capture, duplicate capture/cancel, stale-draft protection, paid thank-you, invalid-token/URL-success rejection, confirmation evidence guards, mobile/desktop layouts, keyboard navigation and print behavior.
- **19 axe scans** passed: the original 15 views/sizes plus unpaid guidance, paid management, and public confirmation at two widths. This is automated accessibility coverage, not a manual screen-reader audit.
- Browser PDF output was one page for both fixture confirmations. Print-media checks and extracted PDF text verified the expected facts and absence of navigation, buttons, drafts, management labels and payment-page URLs. The button's call to `window.print()` was tested separately. Screenshots/PDFs are in ignored `test-results/`.
- The browser harness uses `tests/browser_server.py`, an isolated ignored DB, blank real credentials, in-memory PayPal and mocked Gemini. Fixture drafts are explicitly labelled **not real AI output**. `/__test__/` controls exist only in that test process, never production `create_app`. No provider traffic occurred in these regression checks.

**Genuine running-workspace checks, separate from regressions:**

- An updated local Flask instance on **port 5002**, sharing the existing workspace DB, served the built app without interrupting the user's server on port 5000.
- Two genuine Gemini UI calls returned HTTP 200 with validated wording: an unpaid message and a paid thank-you. Correct saved greeting/signature and exact edited-text copying were checked. No raw message or credential values were printed.
- Existing request activity was stable after refresh. The old unpaid record showed only supported creation activity; the existing paid record showed creation and confirmed payment.
- The existing persisted verified capture rendered in the new public confirmation, at mobile width without overflow, and in a one-page print PDF excluding navigation/drafts. No browser page errors occurred.
- Before/after hashes confirmed **all 3 existing requests, 4 payment attempts and the saved workspace setting were unchanged**. Only the additive empty event table was created; no historical events were invented.
- **No new live PayPal order, buyer login, approval or capture was performed during this sprint.** The new capture/timeline journey was verified with mocks; existing capture rendering used already-persisted verification evidence.

**Not verified:** a newly completed live sandbox journey after this enhancement, native OS print-dialog settings/physical printing, or a full manual assistive-technology audit. Headless print-media/PDF checks are not a claim that every native printer dialog was inspected. Gemini and PayPal readiness flags alone remain insufficient proof of live connectivity.

## Apply and retry locally

Restart the existing backend in its own terminal (Ctrl+C first), from the repository root:

```sh
.venv/bin/python -m flask --app backend:create_app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

Keep `npm run dev` running and reload **http://localhost:5173**. Production assets were also rebuilt. `create_app` automatically creates the additive event table/index; no manual SQL, data reset, seeding, package installation or credential changes are needed. Do not use `tests/browser_server.py` for the real workspace.

### Short manual checklist

1. Open future-due, due-today and overdue fictional requests. Check facts, action, and the exact Nairobi calendar-day count.
2. Save the freelancer name, generate guidance, edit it and copy it. Verify the pasted text is the edited version; no message is automatically sent. If generation fails, check that factual guidance remains available and retry works.
3. Create a fresh fictional USD 1.00 request. Cancel sandbox checkout, refresh details, and verify it remains unpaid with one cancellation event. Retry with the separate Personal sandbox buyer and approve. Do not use real-money accounts.
4. Wait for server-confirmed payment; refresh details/dashboard. Verify paid totals persist and the timeline has one confirmation. Reopening the token link must not offer another payment.
5. Generate the paid thank-you; check that it does not ask for payment. Open its public confirmation, verify amount, name, time and capture reference, then print. In the browser print dialog **turn off Headers and footers** so the private page URL is not added by the browser. Check that navigation, drafts and buttons are absent.
6. Repeat at phone width and with keyboard navigation. An invalid payment token or `?success=true` must never produce a confirmation.

See [the revised 2:50 demo sequence](DEMO.md).
