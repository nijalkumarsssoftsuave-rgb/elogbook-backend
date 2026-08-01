"""Pure hash-chain primitives for the audit trail.

No framework or I/O imports — deterministic functions that are unit-tested on their own.
The audit writer (``audit_writer.py``) uses these to compute each row's hash; the same
functions verify an existing chain.

The chain: ``entry_hash = SHA256( prev_hash || canonical_json(entry) )``. The genesis
row uses ``GENESIS_HASH`` as its predecessor. Because each hash covers the previous
hash, altering or removing any row invalidates every hash after it.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = "0" * 64


def iso_utc(dt: datetime) -> str:
    """Normalise a timestamp to a fixed UTC string for hashing.

    Independent of how the store round-trips timezones: a naive value read back from a
    tz-less column (e.g. SQLite) is treated as UTC, and a tz-aware value is converted to
    UTC — so the write-time and verify-time strings are always byte-identical. Microsecond
    precision, always suffixed ``Z``.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json(data: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, compact separators, non-ASCII preserved.

    ``default=str`` so datetimes/dates/enums serialise stably. Two equal payloads always
    produce byte-identical output, which is what makes the hash reproducible.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_entry_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    """Hash one audit entry onto the chain given its predecessor's hash."""
    material = f"{prev_hash}{canonical_json(entry)}".encode()
    return hashlib.sha256(material).hexdigest()
