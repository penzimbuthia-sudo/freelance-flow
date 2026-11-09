# Submission checklist

Deadline: **November 12, 2026, 11:00 p.m. Africa/Nairobi (UTC+3)**.

## Before recording
- [ ] Configure Gemini locally and run `.venv/bin/python test_ai.py`; confirm a real response from the configured model.
- [ ] Configure sandbox seller app client ID/secret and matching merchant ID. Prepare a separate personal sandbox buyer.
- [ ] Complete the real request → AI draft → edit/copy → buyer approval → server capture → paid dashboard journey.
- [ ] Cancel one checkout and verify the request remains unpaid/retryable.
- [ ] Confirm no secrets appear in browser network responses, frontend bundle, screenshots, or Git history.
- [ ] Use fictional client data. Do not publish local management or change repository visibility without approval.

## Quality and delivery
- [ ] Run `npm run lint`, `npm run build`, `.venv/bin/python -m pytest`, and `npm run test:browser`.
- [ ] Review actual results and blockers in `docs/VERIFICATION.md`.
- [ ] Check mobile UI and console/network errors; verify persistence after refresh/restart.
- [ ] Record the under-three-minute script in `docs/DEMO.md`; hide keys and buyer login details.
- [ ] Check README setup from a fresh checkout and include known limitations and MIT license.
- [ ] Ensure conventional commits are pushed to `main`, no `.env`/database/artifacts are tracked, and repository access meets the hackathon's rules.
- [ ] Fill in the official submission form and confirm the actual event requirements; submission/account changes are the owner's responsibility.
- [ ] Submit before the deadline and retain the confirmation.

Live verification boxes intentionally remain unchecked until performed with real credentials.
