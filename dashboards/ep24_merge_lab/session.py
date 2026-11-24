"""Review sessions for the merge lab UI: autosave, undo/redo, resume, conflict detection (#300).

A researcher's afternoon must survive a reload, a closed tab and a second window. Three rules
make that true:

* every confirmed action is appended to the session file immediately, with a revision number;
* undo/redo move a cursor over the action list rather than deleting anything, so the history is
  the record and a mistaken undo can itself be undone;
* a session remembers which curation run it was opened against and the file's own digest. If the
  file changed underneath the page — another tab, a colleague, a re-run of the CLI — loading
  fails loudly instead of overwriting the newer work.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ACTIONS = ("merge", "keep_separate", "rename", "split", "confirm")


@dataclass(frozen=True)
class Action:
    """One researcher decision as the UI produced it, already validated by the caller."""

    action: str
    category: str
    canonical: str = ""
    members: tuple[str, ...] = ()
    target: str = ""          # split: the label leaving the cluster
    note: str = ""
    at: str = ""
    #: Stable identity for this action, so committing twice does not write it twice.
    uid: str = ""

    def as_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["members"] = list(self.members)
        return payload


@dataclass
class Session:
    """A review session: the actions taken, and where in them the researcher currently stands."""

    session_id: str
    base_run: str
    reviewer: str = ""
    actions: list[Action] = field(default_factory=list)
    #: Number of actions currently in effect. ``cursor < len(actions)`` means undone actions.
    cursor: int = 0
    revision: int = 0
    updated_at: str = ""
    digest: str = ""

    @property
    def effective(self) -> list[Action]:
        return self.actions[: self.cursor]

    @property
    def can_undo(self) -> bool:
        return self.cursor > 0

    @property
    def can_redo(self) -> bool:
        return self.cursor < len(self.actions)

    def add(self, action: Action) -> None:
        """Record a new action, dropping anything that had been undone (a new branch of history)."""
        del self.actions[self.cursor :]
        self.actions.append(action)
        self.cursor = len(self.actions)

    def undo(self) -> Action | None:
        if not self.can_undo:
            return None
        self.cursor -= 1
        return self.actions[self.cursor]

    def redo(self) -> Action | None:
        if not self.can_redo:
            return None
        action = self.actions[self.cursor]
        self.cursor += 1
        return action


def _digest(payload: dict[str, Any]) -> str:
    body = json.dumps(
        {key: value for key, value in payload.items() if key != "digest"},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def session_path(root: Path, session_id: str) -> Path:
    safe = "".join(character for character in session_id if character.isalnum() or character in "-_")
    if not safe:
        raise ValueError("session id must contain at least one alphanumeric character")
    return root / "sessions" / f"{safe}.json"


def new_session(session_id: str, base_run: str, reviewer: str = "") -> Session:
    return Session(
        session_id=session_id,
        base_run=base_run,
        reviewer=reviewer,
        updated_at=datetime.now(UTC).isoformat(),
    )


def save(root: Path, session: Session) -> Session:
    """Write the session atomically, then record its digest so the next read can verify it."""
    session.revision += 1
    session.updated_at = datetime.now(UTC).isoformat()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session.session_id,
        "base_run": session.base_run,
        "reviewer": session.reviewer,
        "actions": [action.as_json() for action in session.actions],
        "cursor": session.cursor,
        "revision": session.revision,
        "updated_at": session.updated_at,
    }
    session.digest = _digest(payload)
    payload["digest"] = session.digest
    path = session_path(root, session.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)  # atomic: a half-written session is never a session
    return session


class SessionConflict(RuntimeError):
    """The file on disk is not the one this page loaded; saving would destroy someone's work."""


def load(root: Path, session_id: str, *, expect_digest: str = "") -> Session:
    """Read a session, refusing to continue when the file changed since it was loaded."""
    path = session_path(root, session_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"session schema {payload.get('schema_version')!r} is not {SCHEMA_VERSION}")
    stored_digest = payload.get("digest", "")
    if stored_digest != _digest(payload):
        raise ValueError("session file is corrupt: its digest does not match its content")
    if expect_digest and stored_digest != expect_digest:
        raise SessionConflict(
            "this session changed on disk after the page loaded it; reload before saving"
        )
    return Session(
        session_id=payload["session_id"],
        base_run=payload["base_run"],
        reviewer=payload.get("reviewer", ""),
        actions=[
            Action(
                action=item["action"],
                category=item["category"],
                canonical=item.get("canonical", ""),
                members=tuple(item.get("members", ())),
                target=item.get("target", ""),
                note=item.get("note", ""),
                at=item.get("at", ""),
                uid=item.get("uid", ""),
            )
            for item in payload.get("actions", [])
        ],
        cursor=int(payload.get("cursor", 0)),
        revision=int(payload.get("revision", 0)),
        updated_at=payload.get("updated_at", ""),
        digest=stored_digest,
    )


def list_sessions(root: Path) -> list[dict[str, Any]]:
    """Sessions on disk, newest first — what the UI offers when a researcher comes back."""
    directory = root / "sessions"
    if not directory.is_dir():
        return []
    sessions = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sessions.append(
            {
                "session_id": payload.get("session_id", path.stem),
                "base_run": payload.get("base_run", ""),
                "reviewer": payload.get("reviewer", ""),
                "actions": len(payload.get("actions", [])),
                "updated_at": payload.get("updated_at", ""),
            }
        )
    return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)
