"""Backend-independent data products consumed by the researcher-facing UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping, Protocol


class ProductKind(StrEnum):
    TABLE = "table"
    RECORDS = "records"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    NETWORK = "network"
    GEODATA = "geodata"
    TIMELINE = "timeline"
    RETRIEVAL = "retrieval"
    REPORT = "report"
    MEDIA = "media"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Stable drill-down link from an analytical object to supporting evidence."""

    record_id: str
    source_url: str | None = None
    artifact_id: str | None = None
    selector: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DataProduct:
    """Logical analysis product, deliberately independent of storage backend."""

    kind: ProductKind
    payload: Any
    project: str | None = None
    dataset: str | None = None
    version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = ()

    def with_evidence(self, refs: Iterable[EvidenceRef]) -> "DataProduct":
        self.evidence = tuple(refs)
        return self


class ProductProvider(Protocol):
    """Capability interface implemented by CSV, MongoDB, NetworkX, etc."""

    def capabilities(self) -> set[ProductKind]: ...

    def get_product(
        self, kind: ProductKind, *, project: str | None = None, query: Mapping[str, Any] | None = None
    ) -> DataProduct: ...


@dataclass(slots=True)
class InMemoryProvider:
    """Small/local-mode provider useful for tests and laptop workflows."""

    products: dict[ProductKind, DataProduct]

    def capabilities(self) -> set[ProductKind]:
        return set(self.products)

    def get_product(
        self, kind: ProductKind, *, project: str | None = None, query: Mapping[str, Any] | None = None
    ) -> DataProduct:
        del query
        product = self.products[kind]
        if project is not None and product.project not in {None, project}:
            raise KeyError(f"product {kind} is not available for project {project!r}")
        return product
