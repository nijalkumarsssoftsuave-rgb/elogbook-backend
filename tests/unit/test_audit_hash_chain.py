"""Unit tests for the audit hash-chain primitives (pure — no DB, no framework)."""

from src.infrastructure.audit.hashing import (
    GENESIS_HASH,
    canonical_json,
    compute_entry_hash,
)


def test_canonical_json_is_key_order_independent():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_canonical_json_serialises_non_str_stably():
    from datetime import date

    out = canonical_json({"due_date": date(2026, 8, 1), "n": 3})
    assert out == '{"due_date":"2026-08-01","n":3}'


def test_entry_hash_is_deterministic():
    entry = {"actor": "jane", "action": "pending_action.create"}
    assert compute_entry_hash(GENESIS_HASH, entry) == compute_entry_hash(GENESIS_HASH, entry)


def test_entry_hash_depends_on_predecessor():
    entry = {"actor": "jane", "action": "pending_action.create"}
    h1 = compute_entry_hash(GENESIS_HASH, entry)
    h2 = compute_entry_hash("f" * 64, entry)
    assert h1 != h2


def test_entry_hash_changes_when_content_changes():
    base = compute_entry_hash(GENESIS_HASH, {"actor": "jane"})
    tampered = compute_entry_hash(GENESIS_HASH, {"actor": "mallory"})
    assert base != tampered


def test_chain_linkage_and_tamper_detection():
    # Build a 3-link chain: each hash feeds the next.
    entries = [{"i": 0}, {"i": 1}, {"i": 2}]
    chain = []
    prev = GENESIS_HASH
    for e in entries:
        h = compute_entry_hash(prev, e)
        chain.append((prev, e, h))
        prev = h

    # Re-walk verifies intact.
    prev = GENESIS_HASH
    for stored_prev, e, stored_hash in chain:
        assert stored_prev == prev
        assert compute_entry_hash(prev, e) == stored_hash
        prev = stored_hash

    # Tamper with the middle entry -> its hash (and every later link) no longer matches.
    _, _, original_mid_hash = chain[1]
    assert compute_entry_hash(chain[1][0], {"i": 99}) != original_mid_hash
