# Testing

Reference for writing tests in CategoristAI. Established in Phase 2; the CSV
ingestion suite (`tests/unit/test_revolut_parser.py`, `tests/e2e/`) is the
worked example, but nothing here is specific to it.

**The governing constraint: the minimum number of tests that still catches a
regression.** A suite is not judged by coverage or count. It is judged by
whether breaking the code makes it go red, and by how quickly a human can read
it. Every test added past that point costs maintenance and buys nothing.

---

## 1. The only criterion that matters

**A test that does not fail when you break the code protects nothing.**

Before considering a suite finished, break the behaviour on purpose and confirm
the right test fails:

```
revert one guarantee  →  run the suite  →  exactly the profile test goes red
```

Do this for every non-trivial guarantee. It takes minutes and is the only way
to know the suite is real. If a deliberate bug leaves everything green, either
the test is asserting the wrong thing or the behaviour is untested — find out
which before moving on.

This is also how you find *gaps you accepted*: if breaking something produces
no failure and you decide that is fine, say so out loud and write it down.
Silent gaps rot; acknowledged ones are a decision.

---

## 2. How many tests

Start from behaviours, not from functions or lines.

- **One case per behaviour branch**, not per input value. Twenty different
  merchant names that all take the same code path are *one* case, not twenty.
  Two of them, if you want a sanity check on variety.
- **One case per past bug.** Every bug that reached you deserves exactly one
  regression case, named after the mistake, so it can never come back quietly.
- **If two tests always fail together, they are one test.**
- **Do not test the framework, the ORM, or the language.** A field that is just
  stored and returned needs no test.
- **Do not test what the type system already guarantees.**

Prefer **one parametrized function over N near-identical functions**. Twenty
cases in one `@pytest.mark.parametrize` read as a table of supported behaviour;
twenty copy-pasted functions read as noise and drift apart over time.

A good ratio to aim for: a handful of test *functions*, a few dozen *cases*.

---

## 3. Two layers, and no third

**Unit — the bulk of the cases.** Pure logic, no database, no network, no
mocks. Most business logic can be tested this way if it is separated properly;
if it cannot, that is usually a design smell worth fixing rather than mocking
around.

**End-to-end — a couple of tests.** The real entry point, the real database,
the real dependencies. Covers wiring: routing, auth, serialisation, the shape
of the response. One happy path and the one or two failure modes a user will
actually hit.

Skip the middle layer by default. "Integration" tests that mock half the world
tend to cost the most and catch the least.

### Do not reach for mocks

A mock encodes your belief about a collaborator. When the collaborator changes,
the mock keeps passing and the suite lies to you. Use the real object whenever
it is cheap:

- Model instances that are never saved need no database.
- Pure functions need nothing at all.
- Prefer passing a small real object over patching an attribute.

Reserve test doubles for things that are genuinely unavailable or unsafe in a
test: outbound network calls, paid APIs, the clock, randomness.

---

## 4. Isolation: roll back, never delete

Tests run against the development database. **The suite must not contain a
single `DELETE`, `TRUNCATE`, or `drop_all`.** A cleanup routine with a wrong
`WHERE` clause destroys real data; a rollback cannot.

Each test runs inside a transaction that is rolled back at teardown, so nothing
it writes is ever committed:

```python
async with engine.connect() as connection:
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint"
    )
    app.dependency_overrides[get_session] = lambda: session
    yield session
    await transaction.rollback()
```

`join_transaction_mode="create_savepoint"` is what makes this work when the
code under test calls `commit()` itself: that commit closes a SAVEPOINT instead
of the outer transaction, which stays under the test's control.

Properties you get for free: no leftovers, no ordering dependencies between
tests, and a crash mid-test rolls back on its own.

**Second line of defence:** name everything the suite creates with a fixed,
searchable prefix (`auto_test_`). If isolation ever leaks, the origin of the
rows is obvious and one query finds them all.

---

## 5. Test data

### Derive it from reality, not imagination

Before writing cases, **analyse real production data** and count what actually
occurs: which types, which states, which combinations, which edge values.
Imagined test data tests imagined bugs. The real distribution tells you which
branches exist and which are hot.

Then add the cases reality does *not* contain but the code guards against —
past bugs, defensive limits — and mark them as such.

### One source of truth

Define cases once, as data, and use them everywhere: as parameters for unit
tests and as the source for any file or payload an e2e test needs.

```python
@dataclass(frozen=True)
class Case:
    id: str                     # names the behaviour, shows up in pytest output
    payload: dict               # the raw input, exactly as the outside world sends it
    outcome: Literal[...]       # what should happen
    ...                         # expected values / error code
```

Expectations live next to their input, so an e2e assertion is derived from the
same list rather than hand-copied — and the two can never drift.

### Anonymise

Test data derived from real data must survive being read by a stranger, and
being committed to a repository.

**Rule:** no real brand, city, employer, person, amount, or date may remain. If
a row can be tied to a specific individual by someone who knows them, it is not
anonymised. Watch especially for the combination — an occupation plus a city is
identifying even when neither alone is.

**Preserve the structure exactly**: quoting, separators, blank fields, encoding
quirks. The structure is what the parser has to survive; the values are not.

Keep generic terms that the logic actually depends on (product names a provider
gives every customer). Losing those would change what the test exercises.

---

## 6. Names

Test names are the specification. Read as a list, they should tell a newcomer
what the system guarantees:

```
card_payment_pending_is_kept
refund_pending_is_skipped
single_char_type_is_not_a_charge
deposit_without_amount_is_reported
```

Name the **behaviour and its expected outcome**, not the function under test.
`test_parse_row_2` tells you nothing when it fails at 2 a.m.

For regression cases, name the mistake. `single_char_type_is_not_a_charge`
records that a substring check once matched a single character — the name
carries the lesson.

---

## 7. What to assert

**Assert behaviour, not implementation.** Assert the outcome a caller can
observe: the returned value, the stored row, the status code, the error code.

- **Error codes, not messages.** Messages are copy and will be reworded; a
  stable machine code is the contract.
- **Structure, not formatting.** Assert the parsed response, not a rendered
  string.
- **Include the identifiers a user needs.** If the contract promises to say
  *which* input failed, assert that the identifier is present and correct — it
  is part of the behaviour, not a detail.

**Logs are usually not behaviour** and asserting on them makes tests brittle.
The exception is a code path whose *entire purpose* is to record something —
there, the log is the behaviour, and skipping it leaves a real gap (see §1:
name the gap if you choose to accept it).

---

## 8. Checklist

1. Analyse real data; list the distinct behaviours it contains.
2. Add one case per behaviour, one per past bug, one per defensive guard.
3. Merge them into as few parametrized functions as stay readable.
4. Unit layer first, without database or mocks; add e2e only for wiring.
5. Isolate with transaction rollback; never write a delete.
6. Anonymise anything derived from real data.
7. Name each case after the behaviour it protects.
8. **Break the code and confirm the right test fails.** Write down any gap you
   decide to accept.
