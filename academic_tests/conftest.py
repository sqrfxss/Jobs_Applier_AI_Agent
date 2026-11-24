"""Isolate synthetic portal rate limits from real user/production state.

A previous integration test suite wrote an auth-request reservation for a
dummy domain to the system-wide database, making subsequent tests fail for
30 minutes. No test may touch that durable production database.
"""
import pytest

@pytest.fixture(autouse=True)
def isolated_portal_access_budget(tmp_path,monkeypatch):
    monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB",
                       str(tmp_path/"synthetic_portal_limits.sqlite3"))
