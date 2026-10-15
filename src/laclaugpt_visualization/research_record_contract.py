"""Accept Analysis-origin research records across declared schema versions (#182).

Why this module exists
----------------------
Data Analysis emits the canonical research record at ``schema_version`` ``1.2.0``
while this repository's published schema declares ``1.1.0``.  A strict ``const``
check therefore rejects a record that is *structurally identical*: on 2026-10-15
the three repositories' ``schemas/research-record.schema.json`` were compared
field by field and found to declare the same thirteen top-level properties and
the same eleven required names, differing only in the version constant.

What this module does, and what it refuses to do
------------------------------------------------
* It declares the versions this consumer accepts **on purpose**, with the date,
  the method and the source of the comparison recorded -- rather than widening a
  constant silently so the mismatch becomes invisible.
* It classifies a version it does not know as ``unknown`` and **keeps the
  original text** so a view can show it.  An unrecognised upstream version must
  surface as a visible unknown; it must never be guessed into acceptance.
* It never rewrites, renames or drops a field.  Acceptance is a statement about
  the version and the required top level; the record itself passes through
  untouched, so provenance, evidence pointers and revisions survive by
  construction rather than by a copy that could omit one.

Contract provenance (read, never imported)
------------------------------------------
========================  ==========================================================
Symbol                    Where it was read
========================  ==========================================================
``schema_version``        Analysis ``schemas/research-record.schema.json`` (``1.2.0``)
``required``              the same file: eleven names, listed below
``SUPPORTED``             this module; mirrored by the local schema's ``enum``
========================  ==========================================================

The mirror is checked by ``tests/test_issue182_research_record_contract.py``, so
the declared set and the enforced set cannot drift apart.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "EXPERIMENTAL_STAGES",
    "EXPERIMENTAL_STAGE_LABEL",
    "PHASE_1_STAGES",
    "REQUIRED_RECORD_FIELDS",
    "SUPPORTED_SCHEMA_VERSIONS",
    "RecordAcceptance",
    "VersionStatus",
    "accept_record",
    "classify_schema_version",
    "stage_status_label",
]

#: Versions this consumer accepts on purpose.  Mirrored by the ``enum`` for
#: ``schema_version`` in ``schemas/research-record.schema.json``.
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.1.0", "1.2.0")

#: The eleven required top-level names, exactly as declared by all three
#: repositories on 2026-10-15.  Order follows the schema; the set is what counts.
REQUIRED_RECORD_FIELDS: tuple[str, ...] = (
    "schema_version",
    "source_url",
    "raw_capture",
    "source",
    "content",
    "intermediate",
    "analysis",
    "human_readable",
    "provenance",
    "review",
    "legacy",
)

#: Stages whose outputs are **experimental Phase 2**, not validated Phase 1
#: methods: the DNA statement coding and the network projection.  Both are
#: capability-gated off in the Phase 1 profile, and when they do appear their
#: outputs must be labelled rather than presented as paper methods.
EXPERIMENTAL_STAGES: frozenset[str] = frozenset(
    {"dna", "dna_statement_coding", "sna", "network_projection"}
)

#: The stages that carry Phase 1 paper semantics.
PHASE_1_STAGES: frozenset[str] = frozenset(
    {
        "summary",
        "context",
        "frame",
        "postprocess",
        "discourse",
        "laclau",
        "palonen",
        "sociotechnical_imaginaries",
    }
)

#: Rendered beside an experimental stage's status.  Deliberately says what it is
#: *not*, because the failure mode this guards against is a provisional network
#: result being read as a validated Phase 1 finding.
EXPERIMENTAL_STAGE_LABEL = "experimental Phase 2 - not a validated Phase 1 method"


class VersionStatus(str, Enum):
    """How a record's declared ``schema_version`` relates to the supported set."""

    SUPPORTED = "supported"
    UNKNOWN = "unknown_version"
    ABSENT = "missing"


@dataclass(frozen=True)
class RecordAcceptance:
    """The outcome of checking one record's version and required top level."""

    status: VersionStatus
    #: The declared version **as text**, including when it is unknown.  A reader
    #: must be able to see the upstream value that was not recognised.
    schema_version: str
    missing_required: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        """True only for a supported version whose required top level is complete."""
        return self.status is VersionStatus.SUPPORTED and not self.missing_required

    def label(self) -> str:
        """A one-line, human-readable statement for a view or a log."""
        if self.status is VersionStatus.ABSENT:
            return "no schema_version declared"
        if self.status is VersionStatus.UNKNOWN:
            return f"unrecognised schema_version {self.schema_version!r} (kept as reported)"
        if self.missing_required:
            return (
                f"schema_version {self.schema_version} but missing required "
                f"field(s): {', '.join(self.missing_required)}"
            )
        return f"schema_version {self.schema_version} (accepted)"


def classify_schema_version(value: Any) -> VersionStatus:
    """Classify a declared version without ever raising or guessing."""
    if value is None or str(value).strip() == "":
        return VersionStatus.ABSENT
    return (
        VersionStatus.SUPPORTED
        if str(value).strip() in SUPPORTED_SCHEMA_VERSIONS
        else VersionStatus.UNKNOWN
    )


def accept_record(record: Mapping[str, Any]) -> RecordAcceptance:
    """Check a canonical record's version and required top level.

    Read-only: nothing is mutated, and an unrecognised version is reported with
    its original text rather than coerced into the supported set.
    """
    raw = record.get("schema_version")
    status = classify_schema_version(raw)
    missing = tuple(name for name in REQUIRED_RECORD_FIELDS if name not in record)
    return RecordAcceptance(
        status=status,
        schema_version="" if raw is None else str(raw),
        missing_required=missing,
    )


def stage_status_label(stage: str) -> str:
    """The label a view must show beside a stage's status.

    Experimental Phase 2 stages get :data:`EXPERIMENTAL_STAGE_LABEL`; Phase 1
    stages get no label, because their status needs no qualification.
    """
    return EXPERIMENTAL_STAGE_LABEL if stage in EXPERIMENTAL_STAGES else ""


def unsupported_versions(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count records by *unsupported* declared version, for a drift line.

    Returns ``{}`` when every record is supported, so a caller can render
    "nothing to report" only when that is genuinely true rather than because the
    check was skipped.
    """
    counts: dict[str, int] = {}
    for record in records:
        status = classify_schema_version(record.get("schema_version"))
        if status is VersionStatus.SUPPORTED:
            continue
        key = str(record.get("schema_version") or "(none)")
        counts[key] = counts.get(key, 0) + 1
    return counts
