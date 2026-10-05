"""Append-only SQLite ledger (AGENTS.md invariant 8).

INSERT only: triggers reject UPDATE and DELETE. A failed write raises `LedgerWriteError`, which
fails the run. Large payloads are stored by SHA-256 in a blob directory;
`detail` holds scalars only.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from emissiongate.contracts import EventKind, LedgerEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    state TEXT NOT NULL,
    agent TEXT,
    kind TEXT NOT NULL,
    tool TEXT,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    duration_ms INTEGER,
    attempt INTEGER,
    payload_sha256 TEXT,
    detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""

Scalar = str | int | float | bool | None


class LedgerWriteError(RuntimeError):
    """The ledger could not record an event. The run must stop."""


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(
        self,
        path: Path,
        run_id: str,
        clock: Callable[[], datetime],
        blob_dir: Path | None = None,
    ) -> None:
        self.path = path
        self.run_id = run_id
        self._clock = clock
        self.blob_dir = blob_dir if blob_dir is not None else path.parent / "blobs"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, isolation_level=None)
            self._conn.executescript(SCHEMA)
        except (sqlite3.Error, OSError) as exc:
            raise LedgerWriteError(f"cannot open ledger at {path}: {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    def _store_blob(self, payload: Any) -> str:
        text = canonical_json(payload)
        digest = sha256_text(text)
        try:
            self.blob_dir.mkdir(parents=True, exist_ok=True)
            blob = self.blob_dir / f"{digest}.json"
            if not blob.exists():
                blob.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise LedgerWriteError(f"cannot store ledger blob: {exc}") from exc
        return digest

    def append(
        self,
        *,
        state: str,
        kind: EventKind,
        agent: str | None = None,
        tool: str | None = None,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        duration_ms: int | None = None,
        attempt: int | None = None,
        payload: Any = None,
        detail: dict[str, Scalar] | None = None,
    ) -> LedgerEvent:
        detail = dict(detail or {})
        for key, value in detail.items():
            if not isinstance(value, str | int | float | bool | type(None)):
                raise ValueError(f"ledger detail {key!r} must be a scalar, got {type(value)}")
        payload_sha = self._store_blob(payload) if payload is not None else None
        ts = self._clock()
        try:
            cur = self._conn.execute(
                "INSERT INTO events (run_id, ts, state, agent, kind, tool, model, prompt_tokens,"
                " completion_tokens, duration_ms, attempt, payload_sha256, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.run_id,
                    ts.isoformat(),
                    state,
                    agent,
                    kind,
                    tool,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    duration_ms,
                    attempt,
                    payload_sha,
                    canonical_json(detail),
                ),
            )
        except sqlite3.Error as exc:
            raise LedgerWriteError(f"ledger write failed: {exc}") from exc
        seq = cur.lastrowid
        if seq is None:
            raise LedgerWriteError("ledger write returned no sequence number")
        return LedgerEvent(
            run_id=self.run_id,
            seq=seq,
            ts=ts,
            state=state,
            agent=agent,
            kind=kind,
            tool=tool,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            attempt=attempt,
            payload_sha256=payload_sha,
            detail=detail,
        )

    def events(self) -> list[LedgerEvent]:
        rows = self._conn.execute(
            "SELECT seq, run_id, ts, state, agent, kind, tool, model, prompt_tokens,"
            " completion_tokens, duration_ms, attempt, payload_sha256, detail"
            " FROM events ORDER BY seq"
        ).fetchall()
        return [
            LedgerEvent(
                seq=r[0],
                run_id=r[1],
                ts=datetime.fromisoformat(r[2]),
                state=r[3],
                agent=r[4],
                kind=r[5],
                tool=r[6],
                model=r[7],
                prompt_tokens=r[8],
                completion_tokens=r[9],
                duration_ms=r[10],
                attempt=r[11],
                payload_sha256=r[12],
                detail=json.loads(r[13]),
            )
            for r in rows
        ]

    def summary(self) -> dict[str, int]:
        events = self.events()
        kinds = Counter(e.kind for e in events)
        llm = [e for e in events if e.kind == "llm_call"]
        return {
            "events": len(events),
            "tool_calls": kinds.get("tool_call", 0),
            "llm_calls": len(llm),
            "prompt_tokens": sum(e.prompt_tokens or 0 for e in llm),
            "completion_tokens": sum(e.completion_tokens or 0 for e in llm),
            "fallbacks": kinds.get("fallback", 0),
            "transitions": kinds.get("transition", 0),
            "errors": kinds.get("error", 0),
        }
