"""Test-session setup — isolates tests from the developer's local .env.

Without this, a local .env pointing at the real MS SQL database (set up for manual
Swagger testing) would leak into test runs, breaking the isolated in-memory tests with
leftover data. Explicit environment variables take priority over .env file values in
pydantic-settings, so setting these before any ``src`` module is imported pins tests to
the safe in-memory backend regardless of what the developer's .env points at.
"""

import os

os.environ.setdefault("ELOG_PERSISTENCE_BACKEND", "memory")
os.environ.setdefault("ELOG_AUTH_STUB_ENABLED", "true")
