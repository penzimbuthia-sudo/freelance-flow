# Existing Neon project: setup and verification

## Status and target

- Organization: `org-lingering-thunder-48580709`
- Project: `billowing-forest-08625291`
- Branch: **production** (a branch name, not permission to deploy publicly)
- Keep the existing **Free** plan. No projects, branches, computes, paid features,
  Neon Auth, Data API, Functions, or storage services were provisioned or enabled.
- **Verified on 2026-11-11:** genuine Neon connection and Flask persistence checks
  passed with the locally saved connection string. SQL independently confirmed
  the project and branch ID `br-wispy-dust-bdi23aex`; the user confirmed in Console
  that this is **production**, in the organization above, on **Free**. Organization,
  branch name and plan were user-confirmed, not independently queried through the
  control-plane API. Endpoint: `ep-divine-frog-bdmlj4uj.c-8.us-east-2.aws.neon.tech`;
  database: `neondb`; direct connection; PostgreSQL 18.6.

## Save credentials privately

1. Sign in to the [Neon Console](https://console.neon.tech). Complete any browser
   authorization yourself; never send a password, authorization token, API key,
   or connection string in chat.
2. Select the organization/project above. Confirm it is on **Free**; do not change
   the plan, create another project, or add a compute. Open **Connect**, select
   **production**, and select the existing database and role. Record the database
   name and endpoint hostname for target verification (neither is a password).
3. For this small local Flask app and its startup migrations, turn **Connection
   pooling off** and copy the **direct** PostgreSQL connection string. This only
   changes the displayed string, not resources or billing. Preserve
   `sslmode=require&channel_binding=require` from the Console. `verify-full` with
   a configured CA store is also supported; do not weaken SSL settings.
4. In your editor create `/home/penzi-mbuthia/freelance-flow/.env.local` containing:

   ```dotenv
   # Paste the real URI here locally, NOT into chat or a shell command.
   DATABASE_URL='<your production branch connection string>'
   PUBLIC_BASE_URL=http://localhost:5173
   APP_HOSTS=localhost,127.0.0.1,[::1]
   ```

   The placeholder is not a usable URI. `.env.local` is already git-ignored.
   Restrict file access with `chmod 600 .env.local`. Do not overwrite `.env` or
   the local SQLite database. Do not use `VITE_DATABASE_URL`, React database
   packages, or client-side SQL. Vite exposes `VITE_` variables to browsers;
   `DATABASE_URL` is consumed only by Flask.

5. Tell the coding agent **“the connection string is saved locally”** and provide
   only the nonsecret selected database name/endpoint hostname and confirmation
   that the project is Free. The next step is read-only target/schema inspection
   before starting Flask against it. Do not paste the URI.

The selected file is loaded explicitly, including under Gunicorn or direct
Python execution. Files are **not merged**: `.env.local` does not automatically
inherit `.env`. PayPal/Gemini credentials are unnecessary for database checks.
An explicitly selected missing file fails before database initialization.
Existing process environment values take precedence; clear stale `DATABASE_URL`
values before switching databases. Tests that explicitly select a SQLite path
cannot accidentally inherit a real environment `DATABASE_URL`.

## Start locally after target/schema inspection

Stop old Flask processes first so requests cannot alternate between databases.
Install dependencies with `.venv/bin/python -m pip install -r requirements-dev.txt`.
Then, from the repository root:

```sh
FF_ENV_FILE=.env.local FLASK_SKIP_DOTENV=1 .venv/bin/python -m flask --app backend:create_app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

`FLASK_SKIP_DOTENV=1` prevents Flask CLI's own automatic `.env`/`.flaskenv` loading;
`backend/config.py` loads the chosen file explicitly. `npm run dev` continues to
proxy `/api` to Flask. Never connect React directly to PostgreSQL.

To return to the preserved SQLite database without changing Neon:

```sh
DATABASE_URL= FF_ENV_FILE=.env FLASK_SKIP_DOTENV=1 .venv/bin/python -m flask --app backend:create_app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload
```

This uses the existing `.env` `DATABASE_PATH`, or the default
`instance/freelance-flow.sqlite3`. Neither command deletes data.

## Data and transaction compatibility

- Psycopg **3.3.8**, synchronous binary driver, matches the existing synchronous
  Flask architecture. There is no async conversion, ORM rewrite, or Node backend.
- URLs are server-only and are never logged or returned. Invalid/unreachable
  PostgreSQL configuration fails closed, without falling back to SQLite. Driver
  exception bodies are suppressed in startup diagnostics and HTTP errors.
- Integer cents preserve exact money values; no floats or currency conversion.
  ISO date-only strings and UTC timestamp strings retain existing timezone and
  timeline behavior. PostgreSQL request/event IDs use explicit `BIGINT` identity
  columns, request foreign keys use `BIGINT`, and inserts use `RETURNING id`.
- Bound parameters remain separate from SQL. A small adapter translates the
  application's static qmark placeholders to Psycopg placeholders. New SQL must
  not contain literal `?` characters or percent operators without updating that
  adapter. User values can contain either character safely.
- PostgreSQL connections use autocommit for standalone reads and explicit
  `READ COMMITTED` transactions for mutations. A shared **transaction-scoped**
  advisory lock is acquired before state reads, preserving the original SQLite
  `BEGIN IMMEDIATE` serialization across payment, cancellation, archive, settings,
  and initialization paths. Lock wait is bounded to 35 seconds; statements within
  these transactions are bounded to 60 seconds. No automatic payment POST retry
  was added. The original persisted keys, five-hour retry boundary, reconciliation
  checks, capture evidence, unique constraints, and one-active-attempt index stay.
- Each Flask request closes its database connection. Reads do not leave idle
  transactions. Prepared statements are disabled for straightforward pooler
  compatibility. A pooled runtime URL can be evaluated later; direct connections
  are appropriate for this low-concurrency, local-only setup and startup DDL.
- Startup runs additive migrations **1 and 2** atomically under the same lock:
  creates missing tables/indexes, adds nullable `archived_at` if absent, and records
  `schema_migrations`. Migration 2 adds PostgreSQL's unique identity-backed
  `attempt_sequence`, the equivalent of SQLite insertion-order `rowid`, for
  latest-attempt guidance. Timestamp ties, UUID sort order and updates to an older
  attempt cannot override the latest inserted attempt. SQLite retains its existing
  `rowid` order without changing attempt rows. A populated legacy PostgreSQL
  attempt table without this sequence fails closed for a reviewed order backfill;
  startup never guesses historical insertion order.
  Repeated startup does not reset, seed, fabricate history,
  overwrite settings, or rewrite payment attempts. Incompatible existing schemas
  fail instead of being dropped. Future non-additive changes need reviewed,
  explicit migrations and backups.
- **No SQLite data is automatically imported into Neon.** Selecting Neon changes
  the active store; existing local requests/settings/payment evidence stay in
  SQLite. If a transfer is wanted, approve a separately reviewed, backup-first,
  all-table import retaining IDs, tokens, idempotency keys, events, archive state,
  settings, attempt insertion order (`rowid` to `attempt_sequence`), and
  identity-sequence positions. Never seed/import over existing data.

## Verification completed (not live Neon)

| Check | Sanitized result |
| --- | --- |
| `npm run lint` | PASS; no lint errors |
| `npm run build` | PASS; 33 modules transformed |
| `.venv/bin/python -m pytest` | **202 passed**; real isolated SQLite + mocked providers/PostgreSQL driver |
| `node --test tests/paymentPresentation.test.js` | **8 passed** |
| `git diff --check` | PASS |
| Built frontend secret scan | PASS; server-only secret values and PostgreSQL connection strings absent |
| Real local Flask HTTP + disposable SQLite | POST fictional request **201**, GET **200**, exact **5010 cents** |
| Settings mutation | PUT/GET **200**; request/attempt/event snapshots unchanged |
| Real Flask process termination/restart | Request, archive state, settings, and factual timeline persisted |
| External payment/AI calls during persistence check | **0**; payment attempts **0** |

The separate-process HTTP check used only a fresh disposable database under
`/tmp/opencode/freelance-flow-persistence-zbzfdszw`, never the workspace database.
The original `instance/freelance-flow.sqlite3` remained byte-for-byte unchanged:

```text
SHA-256: 040a909b7faa11795185a34109258e258358555f672a720a40595407a8b2720d
```

Mocked PostgreSQL checks cover parameter binding, SSL configuration, connection
closure, lock-before-read ordering, commit/rollback including lock failure,
additive migration SQL, and sanitized failures. They **do not prove** PostgreSQL
SQL execution, Neon connectivity, intended-branch identity, or remote persistence.

## Genuine Neon verification (completed 2026-11-11)

These checks used the **real Neon database**, not a mocked PostgreSQL driver.
Every Neon probe and Flask subprocess used exactly:

```sh
FF_ENV_FILE=.env.local FLASK_SKIP_DOTENV=1
```

The URI was loaded through `backend.config.configuration()`, never copied into
commands, output or code. `.env.local` is untracked and ignored by `.gitignore`
line 28 (`.env.*`); its permissions were restricted from `664` to `600`, with
contents unchanged. The frontend was rebuilt with this file present and checked
to ensure the actual server-only secrets/connection string were absent.

| Genuine check | Sanitized result |
| --- | --- |
| Read-only preflight | Project/branch IDs from SQL matched the target; database/role matched configuration; no initial user tables |
| TLS | Client-to-Neon encryption active; `sslmode=require` and `channel_binding=require` retained |
| Initialization | Additive migrations 1 and 2 applied; repeat startup preserved all saved rows |
| Flask HTTP creation | **201**; retained request **1**, client label `FICTIONAL NEON PERSISTENCE CHECK`, service `TEST ONLY - NOT A REAL INVOICE; no payment requested` |
| Flask HTTP retrieval | **200**; **5010 integer cents**, USD, due **2099-12-31**, unpaid, no confirmation/capture |
| Full Flask process restart | First process terminated; a different process retrieved identical request details, settings and timeline from Neon |
| Settings persistence | Saved the already empty effective name through Flask; the actual settings row and timestamps were identical after restart |
| Nonblank settings storage | Fictional nonblank value read back inside a real PostgreSQL transaction, then forcibly rolled back; no retained name change |
| Settings/payment separation | Settings write did not change request, attempt or event snapshots |
| Timeline persistence/idempotency | Exactly one persisted `request_created` event; duplicate event key produced no additional entry |
| Attempt-order regression | Real PostgreSQL, tied timestamps/reverse lexical IDs/older-row update; latest attempt selected correctly; all fictional attempts rolled back |
| Archive/restore | Passed through Flask; archived unpaid public link returned **404**; restore retained facts; timeline unchanged |
| Final retained state | One **archived, unpaid fictional request**, one creation event, blank settings row, migration ledger; **0 payment attempts**, **0 paid requests** |
| Local SQLite | Byte-for-byte unchanged; no import, reset or deletion |

No user data tables existed at the first inspection, so there were **no
pre-existing Neon payment records** to exercise. Snapshot comparisons verified
that settings and restarts did not mutate saved payment facts. The only payment
attempt rows used for ordering regression were fictional, rollback-only storage
fixtures on genuine Neon, not provider responses or live payment operations.
PayPal/Gemini were explicitly disabled in the isolated verification servers;
no order/capture/message endpoints were called. Existing user servers were not
stopped or replaced. The temporary verification servers were stopped afterward.

The creation succeeded on an earlier pass; its record was reused on every retry,
not duplicated. Private snapshots, including bearer tokens, are stored with
restricted permissions under
`/tmp/opencode/freelance-flow-live-neon-eh2qfe1f`. Do not publish those snapshots.
Only sanitized results appear here. No secrets were committed, no Neon CLI was
needed, no plan/resources were changed, and the public app remains undeployed.

### Failures found and resolved

1. The first TLS probe used compute-side `pg_stat_ssl`, which reports false behind
   Neon's terminating proxy. Client libpq `ssl_in_use` confirmed genuine encrypted
   client-to-Neon transport; SSL/channel binding were never weakened.
2. The temporary snapshot harness initially sorted `schema_migrations` by `id`
   instead of `version`. Corrected only the harness; no reset or data deletion.
3. Genuine Flask details returned **500 / UndefinedColumn** because guidance still
   ordered attempts by SQLite-only `rowid`. Fixed using migration 2's PostgreSQL
   insertion sequence, retaining SQLite behavior. Added mocked-driver and SQLite
   tie-order regressions, plus the genuine rollback-only PostgreSQL check above.
4. One full harness run exceeded the initial 120-second tool limit before final
   restart verification. Repeated with a 300-second limit; all checks completed.

### Local use after verification

To use the app locally, start Flask with the documented explicit environment command above and
run `npm run dev`. The test request is archived to keep it out of dashboard totals.
No public deployment, real payment, or SQLite-to-Neon import is authorized by
these checks. The repository's normal backend regression suite remains isolated
SQLite with mocked external services; it is not a live-Neon payment test suite.

## Official documentation consulted

- [Neon Python drivers](https://neon.com/docs/guides/python): Psycopg 3 for synchronous Python.
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling): direct connections for migrations; transaction-pool constraints.
- [Secure Neon connections](https://neon.com/docs/connect/connect-securely): TLS and channel binding.
- [Current Neon CLI reference](https://neon.com/docs/reference/neon-cli): no CLI required here.
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

No Neon CLI command was executed or installed. In particular `neon init`,
`neon deploy`, and `neon.ts` do not configure this existing React/Flask database
connection. If CLI work becomes necessary, check the installed command's
`--help` before execution and use only read-only commands scoped to this existing
project/branch. Pause for the user if browser login is required.
