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

### Fields

```python
logger.info(
    "csv.parse.done",
    total_rows=total_rows,
    parsed=len(outcome.parsed),
    skipped=len(outcome.skipped),
    failed=len(outcome.failed),
    duration_ms=round((time.perf_counter() - started) * 1000, 2),
)
```

Rules:

- Coerce `UUID`/`Decimal`/enums with `str()` — they are not JSON-serialisable.
- Reuse field names across modules: `row_number`, `line_number`, `error_code`,
  `duration_ms`, `user_id`, `account_id`, `filename`. Consistent names are what
  makes cross-module filtering possible.
- `request_id`, `user_id`, `account_id`, `method`, `path` are bound once into
  contextvars and appear automatically — do not pass them by hand.
- Bind per-item context instead of repeating it:
  ```python
  log = logger.bind(row_number=row.number, line_number=row.line)
  ```

---

## 3. Log levels

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
  inside `except`, which attaches `exc_info` for you.
- Derive the level rather than choosing it by hand where possible:
  ```python
  log_event = logger.warning if outcome.failed else logger.info
  log_event("csv.parse.done", ...)
  ```

---

## 4. Exception architecture

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

## 5. The three-tier `except`

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

## 6. Identifying the input

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

## 7. Request context

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

## 8. Logger configuration

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

## 9. Checklist: adding logging to new code

1. `logger = structlog.get_logger(__name__)` at module level.
2. Entry point of a meaningful operation → `info` with its inputs.
3. Per-item detail → `debug`.
4. Summary at the end → `info`, or `warning` if anything failed. Include
   counters and `duration_ms`.
5. Every failure path → a typed exception from `app/core/exceptions.py` with a
   specific reason in `context`.
6. Loop over user data → the three-tier `except` (§5).
7. Anything identifying the input (row number, filename, id) → in the fields.
8. Verify: run the flow, `grep` one `request_id`, and check the chain reads as
   a story. For ingestion it is:
   ```
   upload.received → account.get → csv.read.done → parser.selected
   → csv.format.detected → csv.parse.done → transactions.saved
   → upload.completed → http.request.finished
   ```

---

## 10. Anti-patterns

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
