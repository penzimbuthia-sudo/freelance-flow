# Render Free + existing Neon: preparation, not deployment

**Use one Docker Web Service, not the native Python runtime.** React is compiled
in a pinned Node image; the final pinned Python image contains Flask/Gunicorn and
the built assets, not Node, source dotenv files, or SQLite data. This keeps APIs
and pages on one HTTPS origin and uses no paid disk, Redis, worker, cron, or second
frontend service. No Render service or external account was created/changed.

## Free-only constraints

- Select Render's **Free** compute plan on a free/Hobby workspace. Do not select
  Starter, paid pipelines, persistent disks, paid Redis, or paid preview resources.
  Use the existing **Free Neon** project/production branch; **do not create Render
  Postgres** (its Free database expires after 30 days).
- Render Free sleeps after approximately **15 minutes idle**, can take about a
  minute to wake, has an ephemeral filesystem, and shares **750 instance hours per
  workspace/month**. Deploys, bandwidth and outbound calls have included quotas;
  other services in the workspace consume the same shared allowance.
- **Free compute does not guarantee zero billing if a payment method/paid overage
  is enabled.** Before any approved deployment, review Render Billing, included
  usage and build-pipeline spend limit. For strictly zero charges, do not attach a
  payment method or enable paid overages; accept suspension/build pauses when
  allowances run out. This task did not change any billing/account setting.
- Neon Free also has finite compute/storage/network quotas. Leave scale-to-zero
  and the Free plan unchanged; no keep-alive pinger or paid upgrade. `/healthz`
  does not query Neon, so Render liveness checks do not keep the database awake.
- Gemini is optional. Leave its key blank until you confirm **unbilled free-tier
  access to the configured model**. A key alone does not prove calls are free.
  Preserve `gemini-3.5-flash-lite`; do not guess a replacement or enable billing.
  The quotas below bound calls, not dollar cost on a billing-enabled account.
- PayPal remains **sandbox-only** in both the React SDK and server REST base URL.
  Nothing in this preparation performs a real or sandbox payment.

Render explicitly says its Free instances are for hobby/demo use, not production
reliability. Here “production mode” means hardened serving/configuration, not an
SLA or permission to use real client data.

## Exact Render settings (for a later, explicitly approved deployment)

Do **not** click Create/Deploy yet. When authorized, use:

| Dashboard field | Value |
| --- | --- |
| Service type | **Web Service** |
| Repository / branch | Existing `freelance-flow` GitHub repository / reviewed commit on `main` |
| Language / runtime | **Docker**, not Python |
| Region | **Ohio**, if Free is offered there (near existing Neon `us-east-2`); otherwise an available Free US region |
| Instance type / compute | **Free** |
| Root directory | Blank (repository root) |
| Dockerfile path | `./Dockerfile` |
| Docker build context | `.` |
| Build command | **Not applicable / leave blank**; Render builds the Dockerfile |
| Docker command / start override | **Leave blank** to use Docker `CMD` |
| Effective start command | `gunicorn --config gunicorn.conf.py wsgi:app` |
| Health check path | `/healthz` |
| Auto-deploy / previews | **Off / disabled** until intentional approval |
| Pre-deploy command | Blank (Free has no required shell/job workflow) |
| Disks / extra datastores / scaling | None; one instance, one Gunicorn worker |

### Fix: `failed to read dockerfile: open Dockerfile: no such file or directory`

The reported deploy cloned `fb79b7ffaf1ce8196abedd467e1e006e9163cf58`.
That commit **already contains the regular, tracked file `Dockerfile` at the
repository root**, with exactly that capitalization. Remote `main` and GitHub's
raw file at that commit were verified. `.gitignore` does not exclude it, and
`.dockerignore` explicitly includes it with `!Dockerfile`; neither ignore file
was the cause of this incident.

The service owner confirmed extra trailing characters/slash beside
`./Dockerfile` in Render's **Dockerfile Path** field. Correct the existing
service's **Settings → Build & Deploy** fields to these separate exact values:

| Field | Exact input |
| --- | --- |
| Root Directory | **Empty** — clear the field; do not enter `backend` or `src` |
| Dockerfile Path | `./Dockerfile` — no spaces, extra slash, trailing `/.`, or punctuation |
| Docker Build Context | `.` — a single dot, in its own field |

Render resolves the Dockerfile path and build context relative to Root Directory.
Selecting `backend` hides the root Dockerfile and frontend build inputs. This app
needs the repository root because the multi-stage build copies both `src` and
`backend`. A wrong build context can also cause later `COPY` failures, even when
the Dockerfile itself is found.

**A repository push cannot correct a stored Dashboard field.** Check that the
settings are saved on the same service that produced the error, then manually
retry its build when authorized. Do not create another service, move/duplicate
the Dockerfile, remove secret exclusions, change application code, or reset data.
Clearing the build cache is not a substitute for correcting the path.

Verification performed for this diagnosis: exported the exact reported commit
into a fresh directory, confirmed the root Dockerfile and every repository
`COPY` input, and ran `npm ci --no-audit --no-fund` followed by `npm run build`.
Both passed with an unchanged lockfile and fresh `dist/index.html`, without local
dotenv files, databases, installed modules or prior build output. This used local
Node **25.9.0**, not the Dockerfile's pinned Node 22 container stage.

These checks are distinct from a complete Docker image build. This environment
has no Docker/Podman, so no successful container build or successful Render
redeploy is claimed for this diagnosis. Only this documentation changed; the
existing Dockerfile, ignore rules, application behavior and databases did not.

Gunicorn binds **`0.0.0.0:$PORT`** using `gunicorn.conf.py`; Render's default PORT
is `10000`. It runs one `gthread` worker/four threads, 90-second worker/graceful
timeouts, no idle upstream keep-alive, and bounded worker recycling. Access logs
are off to avoid logging bearer payment URLs. Flask's development server/debugger
is never used by the image or WSGI entry point.

### Build and runtime separation

The Dockerfile performs:

1. `npm ci --no-audit --no-fund` using the existing **unchanged** `package-lock.json`.
2. `npm run build` in a digest-pinned Node 22 build stage.
3. `pip install --no-cache-dir --only-binary=:all: -r requirements.lock` in a
   digest-pinned Python 3.14 runtime. `requirements.lock` pins the known-working
   production transitive dependency graph and includes `requirements.txt`.
4. Copies only Flask code/templates/styles, WSGI/Gunicorn config and compiled
   `dist` to a non-root runtime user. The allowlist `.dockerignore` excludes
   `.env*`, Git, databases, tests, snapshots, installed modules and Python caches.

No build step connects to PostgreSQL or calls Gemini/PayPal. No `ARG`, `VITE_`
secret, or build-time database URL is required. Render makes runtime environment
variables available as potential Docker build arguments: **do not add ARG/COPY
instructions that consume secrets**, and do not upload `.env` as a build secret.
Base image digests were resolved from official Docker Hub metadata; deliberately
refresh them and the Python lock when applying reviewed security updates.

## Server-only runtime environment variables

Set values privately in Render Environment, **not Git, frontend build variables,
chat, or shell command arguments**. Choose the eventual Render subdomain before
first startup so the origin and host can be correct from the start.

| Name | Required value/purpose |
| --- | --- |
| `APP_ENV` | **`production`**; Render's `RENDER=true` also forces hosted safeguards even if APP_ENV was mistakenly left local |
| `DATABASE_URL` | Existing Neon project `billowing-forest-08625291`, production branch `br-wispy-dust-bdi23aex`, existing `neondb`/role. Use the direct URI with `sslmode=require&channel_binding=require`, saved privately; never print it |
| `PUBLIC_BASE_URL` | Exact public HTTPS **origin**, e.g. `https://your-chosen-name.onrender.com`; no path/query/fragment or localhost |
| `APP_HOSTS` | That exact hostname, e.g. `your-chosen-name.onrender.com`; no scheme, wildcards, or copied localhost list. If omitted in hosted mode, it defaults to the configured origin's hostname |
| `SECRET_KEY` | Stable random server secret, at least 32 characters; generator below uses 48 random bytes |
| `ADMIN_USERNAME` | Your single workspace administrator username |
| `ADMIN_PASSWORD_HASH` | Werkzeug default **`scrypt:32768:8:1`** hash, not a raw password; preserve the complete value with `$` delimiters |
| `GOOGLE_API_KEY` | Optional server-only, verified free-tier Gemini key; alternative `GEMINI_API_KEY` supported, GOOGLE takes precedence |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` (existing configured model) |
| `PAYPAL_CLIENT_ID` | Optional sandbox REST app's client ID; only this public identifier can be returned to the sandbox browser SDK |
| `PAYPAL_CLIENT_SECRET` | Optional server-only sandbox app secret |
| `PAYPAL_MERCHANT_ID` | Sandbox business seller merchant ID corresponding to that app |
| `PORT` | Render supplies this; default `10000`. No manual shell interpolation needed |

Do not set `DATABASE_PATH`, `FLASK_DEBUG`, `FF_ENV_FILE`, `VITE_DATABASE_URL`, or
`VITE_` integration keys on Render. Hosted containers use injected environment
variables and do not automatically read dotenv files. Startup **fails before DB
access** if PostgreSQL, HTTPS origin, exact hosts, session secret or administrator
credentials are missing/invalid. Invalid/unreachable PostgreSQL never falls back
to ephemeral SQLite. Local development keeps its original loopback-only mode and
SQLite option when no hosted/auth configuration is selected.

Generate login settings **locally**, without exposing them, using:

```sh
.venv/bin/python scripts/create_hosted_secrets.py
```

This prompts for a username and a unique password (16+ characters, no echo), then
writes **`.env.render.local` with mode 600**. It refuses to overwrite an existing
file and never stores/prints the password. The file is ignored by Git and the
Docker context. Open it privately in your editor to transfer the three named
values to Render when authorized. Keep the secret stable across restarts; changing
the secret invalidates cookies, and changing the username/hash revokes all existing
server sessions on their next request. No actual administrator credentials were
generated/set by this preparation; test credentials were ephemeral and fictional.

For a local hosted-mode rehearsal only, use a **separate** ignored environment file
combining your private Neon URI, login settings, and the planned HTTPS origin/host,
then explicitly select it with `FF_ENV_FILE=... FLASK_SKIP_DOTENV=1`. Secure cookies
need a real HTTPS browser origin/reverse proxy; merely browsing `http://localhost`
is not an end-to-end secure-cookie test. Never overwrite `.env.local` to rehearse.

## Authentication and request safety

- `/login` is a server-rendered, escaped form with login CSRF protection and a
  restricted same-origin redirect. There is no public sign-up, default password,
  or browser/localStorage authentication shortcut.
- The `__Host-ff_session` cookie is **Secure, HttpOnly, SameSite=Lax, Path=/**,
  with no Domain attribute. It contains signed session state plus an opaque random
  session identifier; PostgreSQL stores only its hash, credential-version digest
  and **8-hour absolute expiry**. The CSRF nonce rotates on login.
- All management pages, including direct frontend routes **and `/index.html`**,
  redirect unauthenticated visitors to login. All known management APIs, including
  settings, AI, archive/restore, health and auth-session info, require server-side
  authentication and return JSON **401**, even for loopback/forwarded requests.
- Authenticated management mutations and logout require a matching
  **`X-CSRF-Token`** and reject a supplied cross-origin Origin. React obtains the
  token from authenticated `GET /api/auth/session` and uses only relative `/api`
  URLs with same-origin cookies. Tokens/credentials are never build variables.
- **Sign out** in the management header calls CSRF-protected
  `POST /api/auth/logout`, deletes that server-side session and clears the cookie.
  Replaying the old signed cookie is rejected. Other sessions remain independent.
- `/pay/:token`, built public assets, and `/api/public/*` stay accessible without
  admin login or admin CSRF. They retain bearer-token secrecy, origin checks,
  sandbox-only checkout, archive blocks and existing payment/idempotency safeguards.
- Unknown `/api` paths, including `/api` itself and non-GET requests, always return
  JSON **404**, not index.html. Missing assets return 404, not a SPA document.
- Login is bounded to **10 attempts globally per 15 minutes** before password
  hashing. Hosted/authenticated AI is bounded to **6 requests globally per minute**
  (including errors), with existing bounded upstream timeout/retry behavior.
  Quotas persist in Neon across workers/restarts; spoofing forwarded IP headers
  cannot bypass them. `429` includes Retry-After. Global quotas can be exhausted by
  an attacker, so accept temporary login denial; this is a minimal demo, not a
  distributed bot-protection service. No paid Redis is needed.
- Request bodies are capped at 16 KiB. No proxy-derived host/origin is trusted:
  payment links come from the validated HTTPS origin, exact Host validation is
  enforced, and arbitrary X-Forwarded headers cannot grant management access.
- Additive migration **3** creates only `management_sessions`, `request_limits`
  and an expiry index. Expired login metadata is cleaned up on successful login;
  no business/payment/history data is reset, imported, deleted or rewritten.
  Existing integer cents, archive state, settings and factual timelines remain.

## Verification and remaining blockers

The normal backend suite uses isolated SQLite and mocked providers/driver checks.
The separate Gunicorn/Neon check below used the **genuine existing database**.
Neither kind of test performed a PayPal payment or Gemini API request.

| Check | Result |
| --- | --- |
| Lockfile build | `npm ci --no-audit --no-fund`, lint and Vite production build passed; npm lock unchanged |
| Backend | **251 passed**, including authentication, configuration, payment/archive regressions, secret-file generation and real Gunicorn smoke |
| Frontend units | **12 passed** (presentation plus same-origin/CSRF/session-expiry API helper checks) |
| Chromium regressions | **17 passed** on the complete rerun; isolated SQLite and mocked providers, not real payments/AI |
| Python production lock | Fresh-resolution dry run with binary-only wheels succeeded on Python 3.14/Linux |
| Base images | Both pinned digests matched official Docker Hub tags and include Linux AMD64 manifests |
| Real Gunicorn + disposable SQLite | Direct management routes, login, cookie flags, CSRF, public payment page/data/assets, JSON API 404s, logout/replay rejection and process restart passed |
| Real Gunicorn + Neon, hosted mode | Same routing/auth checks passed; existing fictional request **1**, settings, factual timeline and authenticated session survived a full Gunicorn restart |
| Genuine Neon identity/TLS | Expected project/production branch IDs and `neondb` matched; libpq client TLS active |
| Real Neon business preservation | All pre/post request, attempt, event and settings rows identical; no new/imported business records. Existing archived token data correctly returned 404 without requiring login |
| Secret/data preservation | `.env.local` remains ignored/private and its contents unchanged; original SQLite unchanged; actual server-only secrets absent from rebuilt frontend |
| Docker image execution | **Not run:** this environment has neither Docker nor Podman. Both build components and actual Gunicorn serving were checked, but the complete image still needs a Docker build/run on an approved machine |
| Render/public HTTPS deployment | **Not performed**, intentionally. No Render account/service, DNS, billing, plan or external configuration changed |

The production smoke simulates Render's TLS-terminating proxy by sending the
configured public Host/Origin to Gunicorn over loopback HTTP and explicitly
transporting the Secure cookie only in that test. This verifies server cookie
flags and authentication behavior, not a publicly deployed Render TLS certificate.
Public active-token data was checked against disposable SQLite; the retained
Neon fictional token remains archived, and its denial was verified unchanged.

One initial smoke run timed out during graceful shutdown due to idle Gunicorn
keep-alive sockets; upstream keep-alive was disabled and restart checks passed.
The first existing Chromium regression run passed 16 checks but hit a modal timing
race in the draft-navigation test: it clicked the backdrop before waiting for the
dialog to open. Added the missing visibility wait without changing draft behavior;
the affected test and then the full **17-test** browser suite passed on rerun.
Real deployment still requires your chosen Render HTTPS hostname, privately
generated administrator credentials/stable session key, confirmation of current
free-only account quotas/billing settings, and a Docker-capable machine to verify
the complete image. Commit/push or deployment is not automatic for this task.

## Re-run locally

```sh
npm ci --no-audit --no-fund
npm run lint
npm run build
.venv/bin/python -m pytest
node --test tests/api.test.js tests/paymentPresentation.test.js
```

On an approved Docker-capable machine, `docker build -t freelance-flow:local .`
needs no credentials. Only a later `docker run --env-file <private-runtime-file>
-e PORT=10000 -p 127.0.0.1:10000:10000 freelance-flow:local` supplies runtime secrets;
use an HTTPS proxy for browser login. Do not publish the image/service or weaken
Secure cookies to make an HTTP-only login work.

Official references consulted: [Docker on Render](https://render.com/docs/docker),
[Free limits](https://render.com/docs/free),
[web service ports/TLS](https://render.com/docs/web-services#port-binding), and the
[HTTP health-check Host behavior](https://render.com/docs/health-checks), plus the
[root-relative Dockerfile/context rules](https://render.com/docs/monorepo-support#root-relative-settings) and
[Neon setup/security references](NEON.md#official-documentation-consulted).
