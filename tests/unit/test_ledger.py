import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from emissiongate.core.ledger import Ledger, LedgerWriteError


def _clock() -> datetime:
    return datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite", "run-test", _clock)


def test_append_is_monotonic_and_hashes_payload(ledger: Ledger) -> None:
    a = ledger.append(state="SCOPED", kind="transition")
    b = ledger.append(state="COLLECTING", kind="tool_call", tool="cur.load", payload={"rows": 3})
    assert (a.seq, b.seq) == (1, 2)
    assert b.payload_sha256 and len(b.payload_sha256) == 64
    assert (ledger.blob_dir / f"{b.payload_sha256}.json").exists()
    assert [e.seq for e in ledger.events()] == [1, 2]


def test_llm_call_records_tokens(ledger: Ledger) -> None:
    ledger.append(
        state="DELIVERING",
        kind="llm_call",
        model="gpt-oss:20b@medium",
        prompt_tokens=120,
        completion_tokens=40,
        duration_ms=900,
        attempt=1,
    )
    summary = ledger.summary()
    assert summary["llm_calls"] == 1
    assert summary["prompt_tokens"] == 120


def test_update_and_delete_are_rejected(ledger: Ledger, tmp_path: Path) -> None:
    ledger.append(state="SCOPED", kind="transition")
    conn = sqlite3.connect(tmp_path / "ledger.sqlite")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE events SET state = 'X'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM events")
    conn.close()


def test_failed_write_raises(ledger: Ledger) -> None:
    ledger.close()
    with pytest.raises(LedgerWriteError):
        ledger.append(state="SCOPED", kind="transition")


def test_detail_must_be_scalar(ledger: Ledger) -> None:
    with pytest.raises(ValueError):
        ledger.append(state="SCOPED", kind="transition", detail={"bad": [1, 2]})  # type: ignore[dict-item]
