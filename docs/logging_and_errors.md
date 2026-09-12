# Logging & Error Handling

Reference for adding logging and errors to CategoristAI. Follow it when writing
any new service, endpoint, or parser. Established in Phase 2 while hardening the
CSV ingestion flow; the ingestion flow is the worked example throughout.

**The goal:** when something breaks, a developer must be able to answer *what
happened, where, to which input, and why* from the logs alone — without
re-running the request.

---

## 1. Core principles

1. **The event name is a constant; the variation goes into fields.**
   `logger.info("csv.row.failed", row_number=431)` — never
   `logger.info(f"Row {n} failed")`. Only the first form can be grouped,
   counted, and alerted on.
2. **An error must always name a specific reason.** "Unknown type" is not a
   reason. Which value, in which column, of which row.
3. **Never hide an error.** It reaches the user as a readable message with a
   stable code — never as a stacktrace, and never silently swallowed.
4. **Bad user data and bugs in our code are different things.** They get
   different exception types, different log levels, and different responses.
5. **One bad row must not cost the other 2000.** Row-level problems are
   collected and reported; the import completes.
6. **Fail loud on broken invariants.** If the code guarantees something and it
   turns out false, that is a 500 with a traceback — not a silent fallback.

---

## 2. Structured logging

### Event naming

Dotted, lowercase, `subject.action` or `subject.thing.action`, past tense for
things that happened:

```
app.startup            upload.received        csv.row.parsed
app.shutdown           upload.completed       csv.row.skipped
http.request.finished  csv.read.done          csv.row.failed
http.app_error         csv.parse.done         csv.row.crashed
parser.selected        csv.format.detected    transactions.saved
```

Group by prefix so `grep "csv.row."` gives you the per-row story and
`grep "upload."` the lifecycle.

**Cardinality follows the event, not the module.** The prefix is singular when
the event concerns one entity and plural when it concerns a set or a batch:
`account.created`, `transaction.updated`, but `accounts.listed` and
`transactions.saved`. One module legitimately emits both. A cheap `debug` probe
that fires *before* the query keeps the short `subject.verb` form — `user.get`,
`account.get` — because nothing has happened yet to put in the past tense.

### Fields

```python
logger.info(
    "csv.parse.done",
    total_rows=total_rows,
    parsed=len(outcome.parsed),
    skipped=len(outcome.skipped),
    failed=len(outcome.failed),
    duration_ms=elapsed_ms(started),
)
```

Rules:

- Coerce `UUID`/`Decimal`/enums with `str()` — they are not JSON-serialisable.
- Reuse field names across modules: `row_number`, `line_number`, `error_code`,
  `duration_ms`, `user_id`, `account_id`, `filename`. Consistent names are what
  makes cross-module filtering possible.
- `duration_ms` is always `elapsed_ms(started)` from `app.core`, with `started`
  taken from `time.perf_counter()`. Never write the arithmetic at the call site:
  the helper fixes the precision, so durations from different modules stay
  comparable, and it keeps the wall clock — which NTP can move backwards — out
  of the measurement.
- `request_id`, `user_id`, `account_id`, `method`, `path` are bound once into
  contextvars and appear automatically — do not pass them by hand.
- Bind per-item context instead of repeating it:
  ```python
  log = logger.bind(row_number=row.number, line_number=row.line)
  ```

---

## 3. Secrets and sensitive data

A log line outlives the request that produced it and travels further: stdout →
Docker's json-file driver → whatever ships it onward, each hop with its own
retention and its own access list. Everything in §2 pushes you to put *more*
into fields. This section is the boundary.

### Never logged — any level, any field

| Category | Examples |
|---|---|
| Credentials | plaintext password, password hash (`hashed_password`), API key, `Authorization` header |
| Tokens | access token, refresh token, any JWT or fragment of one, session id |
| Recovery | password-reset token, email-confirmation token, OTP / 2FA code |

The password *hash* is on the list deliberately. It is not a password, but it is
an offline-crackable artefact: it belongs in the database, not in a log
aggregator with looser retention and a wider audience.

The rule is absolute: a secret is never a field value — not truncated, not
masked, not "only the first four characters".

### Why masking the middle does not work for a secret

The tempting shape is `pa****rd`: keep the ends so one value can be followed
across lines. It fails for secrets, for two unrelated reasons.

- **Passwords are low-entropy.** First character, last character, and length
  remove most of the search space for a human-chosen password. That is not
  redaction, it is a hint.
- **Token ends carry nothing.** Every JWT from one issuer opens with the same
  base64 header (`eyJhbGciOi…`), so the prefix distinguishes nothing; the tail
  is signature bytes. You leak material *and* still cannot correlate.

### Correlating without the secret

The goal behind masking is legitimate — follow one token through a chain of log
lines. Take it from an identifier instead of from the value.

1. **Prefer an id the model already has.** A refresh-token row has a primary key
   and a `jti`; both are designed to be public handles. Log that.
2. **Otherwise log a fingerprint** — a truncated digest, stable across lines and
   irreversible:

```python
def fingerprint(value: str) -> str:
    """Stable, non-reversible handle for correlating a secret across log lines."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]

log.warning("auth.refresh.rejected", token_fp=fingerprint(token), reason="expired")
```

Twelve hex characters join lines within one incident and are useless as an
attack surface. Suffix the field `_fp` so nobody mistakes it for the value.

### Sensitive identifiers — masking is right here

Not everything private is a credential. An email, IBAN, card PAN, or phone
number is an *identifier*: a human reading the log has to recognise which
account is affected, and knowing it grants no access. Keep the ends, drop the
middle:

```python
mask_email("valentin-4@mail.ru")        # -> "va***@mail.ru"
mask_tail("GB29NWBK60161331926819")     # -> "****6819"
```

Prefer `user_id` wherever it exists — unambiguous and carrying nothing. Fall
back to a masked identifier exactly when the id is what you do not have yet: a
failed login names an account that may not even exist.

`fingerprint` lives in `app/core/logging.py`, next to the processors, so there
is one implementation to audit. `mask_email` / `mask_tail` belong beside it and
are to be written when the first such field appears — today `users.login` is a
username, not an email, and no email, IBAN, or PAN is stored anywhere. If logins
ever become emails, `auth.login.*`, `auth.register.*` and `user.get_by_login`
are the call sites that must switch.

### Auth logs may be specific; auth responses may not

The log is ours, the response is the attacker's. The log line is allowed to know
more:

```python
# response in both cases: 401, "Invalid email or password"
log.warning("auth.login.failed", email=mask_email(email), reason="user_not_found")
log.warning("auth.login.failed", email=mask_email(email), reason="bad_password")
```

That distinction must not escape. A different message, a different `ErrorCode`,
or a measurably different response time turns the endpoint into an account
enumeration oracle. §4 still applies — a failed login is `warning`, the user's
input is wrong — and so does §7: identify the input, but identify it masked.

### The pipelines we do not write

Our code is not the only thing logging. Keep `sqlalchemy.engine` above `INFO` in
production (§9 covers per-logger levels): at `INFO` it echoes statement
parameters, and an `INSERT INTO users` carries the hash. The same holds for any
HTTP client configured to log request headers — that is where the
`Authorization` header leaks.

---

## 4. Log levels

The rule, in one line each:

| Level | Meaning | Who acts | Volume scales with |
|---|---|---|---|
| `debug` | Per-item trace for reproducing one request | nobody | row count |
| `info` | Lifecycle milestone, expected outcome | nobody | request count |
| `warning` | **The user's data or request is wrong** | the user | bad input |
| `error` | **Our code is wrong.** Always a traceback | the developer | bugs |

Test: *who is supposed to do something about this line?* Nobody → `info`.
The user → `warning`. You → `error`.

Consequences to respect:

- An expected skip is **never** `warning`. A pending Card Refund is normal.
- An unrecognised value is **never** `debug`. It means a gap in our rules.
- `error` without a traceback is nearly useless — use `logger.exception(...)`
  inside `except`, which attaches `exc_info` for you. The one exception is a
  re-raise: see *one incident, one traceback* below.
- Derive the level rather than choosing it by hand where possible:
  ```python
  log_event = logger.warning if outcome.failed else logger.info
  log_event("csv.parse.done", ...)
  ```

### One incident, one traceback

An exception that is logged and then re-raised passes several layers, and if
each one calls `logger.exception` the same stack is written three times. That
is not triple the evidence — it is one incident that now looks like three, and
every `error`-rate alert counts it three times.

The traceback belongs to the **outermost** handler, the one that turns the
exception into a response: `http.unhandled_exception`. Every layer below it
logs `logger.error` **without** `exc_info`, carrying only what the outer layer
cannot see — the transaction id, the field names, the SQLSTATE, how long the
request ran. The lines are joined by `request_id`, which is what it is for.

```python
except IntegrityError:
    # Inner layer: context, no traceback. Re-raised, so it will be logged.
    log.error("transaction.update.failed", fields=fields, sqlstate=state)
    raise
```

The rule applies only when the exception **escapes**. Where it is swallowed —
tier 3 of the three-tier `except` in §6, which keeps the import running — that
layer is the last one that will ever see it, so it must use
`logger.exception`.

---

## 5. Exception architecture

All domain exceptions live in `app/core/exceptions.py` and inherit `AppError`.

```python
class AppError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL_ERROR   # stable machine-readable id
    http_status: int = 500
    message: str = "Unexpected application error"

    def __init__(self, message: str | None = None, **context): ...
    def log_fields(self) -> dict:                # -> straight into structlog
        return {"error_code": str(self.code), **self.context}
```

Why each part:

- **`code`** is the identity. Two errors may read similarly; their codes differ,
  so the client and the logs can always tell them apart. Codes live in
  `ErrorCode` (`app/core/constants.py`).
- **`context`** is a kwargs bag, not a formatted string — it flows into
  structlog as fields and into the response `details` unchanged.
- **`http_status`** on the class means the handler needs no mapping table.

### Three planes

| Base class | Meaning | Effect |
|---|---|---|
| `UploadError` | File level — nothing can be imported | Aborts the request, HTTP 4xx |
| `RowError` | Row level — this row is bad | Collected, import continues |
| `InvariantError` | "This cannot happen" — a bug | HTTP 500, traceback, fail loud |

Adding a new error: pick the plane, add an `ErrorCode`, subclass, give it a
`message` written **for the end user**. Put internals in `context`, never in the
message text.

```python
class UnknownSavingOperationError(RowError):
    code = ErrorCode.ROW_UNKNOWN_SAVING_OPERATION
    message = "Unknown savings operation in the Description column"

# raise site
raise UnknownSavingOperationError(description=in_tr.description)
```

**Never interpolate a model into a message** (`f"Unknown type {tr}"`).
`BaseModel.__repr__` dumps every column including `raw_data`. Pass the specific
fields through `context`.

### Responses

`app/api/errors.py` registers handlers for `AppError`, `HTTPException`,
`RequestValidationError`, and bare `Exception`. Every error response has the
same envelope:

```json
{
  "code": "csv_format_unknown",
  "message": "CSV header does not match any known export format",
  "request_id": "8f316f07f1174b4fbb1435b5aea84dc5",
  "details": {"headers": ["Foo", "Bar"]}
}
```

The catch-all `Exception` handler returns a fixed generic message and **never**
the exception text — a database error can carry SQL. The `request_id` is the
bridge: the user quotes it, you grep the traceback.

---

## 6. The three-tier `except`

The most important pattern in the codebase. Use it wherever a loop processes
user-supplied items (`InstitutionParserBase.parse` is the reference
implementation).

```python
for row in rows:
    log = logger.bind(row_number=row.number, line_number=row.line)
    try:
        ...

    except RowError as ex:
        # Tier 1: a described data problem. No traceback needed.
        log.warning("csv.row.failed", row=row.data, **ex.log_fields())
        outcome.failed.append(_issue(row, ex.code, ex.message))

    except ValidationError as ex:
        # Tier 2: pydantic rejected it - also bad data, not a bug.
        message, field_name = format_validation_error(ex)
        log.warning("csv.row.failed", row=row.data, reason=message)
        outcome.failed.append(...)

    except Exception:
        # Tier 3: OUR BUG. Keep the traceback, keep importing, and never
        # let the stacktrace reach the client.
        log.exception("csv.row.crashed", row=row.data)
        outcome.failed.append(_issue(row, ErrorCode.ROW_INTERNAL_ERROR,
                                     "Internal error while processing this row"))
```

Order matters: specific first, `Exception` last. Tier 2 must be explicit,
otherwise a pydantic error gets misfiled as a crash.

**Why tier 3 exists.** A blanket `except Exception` that stores `str(ex)` turns
a `KeyError: 'State'` into `{"error": "'State'"}` — cause invisible, traceback
gone. That happened in Phase 2 and cost real debugging time. Now the same bug
produces a full structured traceback with the row number, while the import
still completes.

---

## 7. Identifying the input

An error the user cannot locate in their file is only half-reported.

- `parse_csv` must not return bare `dict`s — the position is lost immediately.
  Carry it in a `CsvRow` (`app/services/institution_parser/rows.py`):
  - `number` — index among data rows, what the user counts;
  - `line` — `DictReader.line_num`, the physical line, which differs as soon as
    a quoted field contains a newline. Use `line_num`, not `enumerate`.
- Both numbers go into every log line and every `UploadIssue`.

### Partial-failure responses

Batch endpoints return **HTTP 200** with a per-row report, not an all-or-nothing
error. Separate the three outcomes — they are genuinely different:

```python
class UploadCounters(BaseModel):
    total_rows: int; parsed: int; saved: int
    duplicates: int; skipped: int; failed: int
```

- `skipped` — expected, deliberate (a pending refund). Not a problem.
- `failed` — something went wrong with that row. Needs attention.
- `duplicates` — already imported. Normal on re-upload.

Cap the issue lists (`issues_truncated` flag) so a fully broken file cannot
return megabytes of JSON. **Counters stay exact; only the lists are trimmed**,
and the logs keep everything.

---

## 8. Request context

`RequestContextMiddleware` (`app/api/middleware.py`) binds `request_id`,
`method`, `path` into structlog contextvars and echoes `X-Request-ID` on the
response. `get_current_user` binds `user_id`. Everything logged during the
request inherits them, so one upload is one `grep`.

Two rules when touching it:

- `clear_contextvars()` **first** — contextvars survive on a reused task, and
  without the clear the previous request's fields leak into the next one.
- Bindings made *inside* an endpoint do not propagate back out to the
  middleware. Bind request-wide context in the middleware or a dependency.

---

## 9. Logger configuration

`app/core/logging.py`. Console in dev, JSON in prod, both from one handler.

The key point: structlog and stdlib `logging` are separate pipelines. Our code
calls structlog; uvicorn and SQLAlchemy call stdlib. `ProcessorFormatter` with
`foreign_pre_chain` merges them, so third-party records get our format *and*
inherit `request_id`. A `PrintLoggerFactory` setup can never do this.

Processors and why they are there:

| Processor | Purpose |
|---|---|
| `merge_contextvars` | Injects `request_id` & co. Must be first. |
| `filter_by_level` | Honours per-logger levels (silences `sqlalchemy.engine`). |
| `add_logger_name` | `logger="app.services.csv_service"`. |
| `PositionalArgumentsFormatter` | Keeps legacy `%s`-style calls rendering. |
| `TimeStamper(iso, utc)` | UTC matters once deployed to the Pi. |
| `UnicodeDecoder` | Stray bytes from a CSV cannot break serialisation. |
| `ExceptionRenderer(show_locals=False)` | Traceback in JSON without dumping every variable. |
| `CallsiteParameterAdder` | module/func/line — **dev only**, walks the stack. |

Gotcha: `cache_logger_on_first_use=True` means a second `structlog.configure()`
will not reach already-cached loggers. `setup_logging()` is therefore guarded by
`_configured`, and `configure_third_party_loggers()` is re-run in `lifespan`
because uvicorn reinstalls its handlers after importing the app.

Settings (`LoggingSettings`, env prefix `LOG_`): `LOG_LEVEL`, `LOG_FORMAT`,
`LOG_FILE` (off by default — stdout is the primary sink; Docker rotates it, and
writing every line to a Pi's SD card wears it out).

---

## 10. Checklist: adding logging to new code

1. `logger = structlog.get_logger(__name__)` at module level.
2. Entry point of a meaningful operation → `info` with its inputs.
3. Per-item detail → `debug`.
4. Summary at the end → `info`, or `warning` if anything failed. Include
   counters and `duration_ms`.
5. Every failure path → a typed exception from `app/core/exceptions.py` with a
   specific reason in `context`.
6. Loop over user data → the three-tier `except` (§6).
7. Anything identifying the input (row number, filename, id) → in the fields.
8. Every field re-read against §3: no credential, no token, no hash. A secret is
   hidden outright and correlated by `*_fp`; an email or account number goes in
   masked.
9. Verify: run the flow, `grep` one `request_id`, and check the chain reads as
   a story. For ingestion it is:
   ```
   upload.received → account.get → csv.read.done → parser.selected
   → csv.format.detected → csv.parse.done → transactions.saved
   → upload.completed → http.request.finished
   ```

---

## 11. Anti-patterns

Each of these was a real bug in this repo.

| Don't | Why | Do |
|---|---|---|
| `raise ValueError(f"Unknown type {x}")` | Three call sites had byte-identical text — unresolvable from the response | Typed exception with an `ErrorCode` |
| `except Exception: errors.append(str(ex))` | `KeyError: 'State'` became `{"error": "'State'"}` | Three-tier `except`, `logger.exception` in the last |
| `logger.info(f"Saved {n} for {user.id}")` | Not filterable, not countable | `logger.info("transactions.saved", saved=n, user_id=str(user.id))` |
| `return "Unknown transaction to skip"` | A failure returned through the *skip* channel | `SkipReason` enum; unknown → `raise` |
| `parse_csv() -> list[dict]` | Row position lost at the first function | Return `CsvRow` carrying `number` and `line` |
| Per-row format detection | Unrecognised file → N identical errors | Detect once from the header → one 422 |
| `logger.warn(...)` | Deprecated alias | `logger.warning(...)` |
| Interpolating a model into a message | `__repr__` dumps every column incl. `raw_data` | Named fields via `context` |
| Blanket `# noqa` to satisfy an ordering hunch | The constraint was imaginary; `get_logger` is lazy | Verify the constraint first |
| `logger.info("login", password=pw)` | A log line outlives the request and travels further than the DB | Never log the secret; log the outcome |
| `token[:8] + "..."` to trace a token | JWT prefixes are identical per issuer — leaks material, correlates nothing | `token_fp=fingerprint(token)` |
| Masking a password as `pa****rd` | Passwords are low-entropy; ends plus length are a hint, not redaction | Do not log it at all |
| Distinct codes for "no such user" and "wrong password" | Turns the endpoint into an enumeration oracle | One generic 401; keep the reason in the log |
