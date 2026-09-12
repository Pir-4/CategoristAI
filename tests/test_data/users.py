"""User and auth test data: the values the suite sends and expects.

Kept next to `revolut_cases.py` for the same reason - defined once, used by
both layers, so a unit assertion and an e2e assertion can never drift apart.
"""

DEFAULT_PASSWORD = "auto_test_password"

# The complete public surface of a user. Asserted literally, never derived
# from ``UserRead.model_fields`` - a field added to the schema by mistake
# would then be "expected" by the very test meant to catch it.
USER_READ_FIELDS = frozenset({"id", "login", "created_at"})
