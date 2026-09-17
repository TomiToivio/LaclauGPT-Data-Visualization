"""Product-provider adapter for AC/DT result envelopes.

It lets the existing visualization plugin registry consume legacy/current AC/DT outputs
without a storage-specific implementation. Multiple results of the same ProductKind are
kept as a list rather than silently merged into one analytical object.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .acdt_compat import result_products
from .products import DataProduct, ProductKind


class ACDTResultProvider:
    def __init__(self, results: Iterable[Mapping[str, Any]]) -> None:
        grouped: dict[ProductKind, list[DataProduct]] = defaultdict(list)
        for result in results:
            for kind, product in result_products(result).items():
                grouped[kind].append(product)
        self._products = dict(grouped)

    def capabilities(self) -> set[ProductKind]:
        return set(self._products)

    def get_product(
        self,
        kind: ProductKind,
        *,
        project: str | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> DataProduct:
        del query
        candidates = self._products[kind]
        if project is not None:
            candidates = [item for item in candidates if item.project in {None, project}]
        if not candidates:
            raise KeyError(f"no AC/DT product for {kind.value!r} and project {project!r}")
        if len(candidates) == 1:
            return candidates[0]
        return DataProduct(
            kind=kind,
            payload=[item.payload for item in candidates],
            project=project,
            dataset=None,
            version="acdt-provider/1.0",
            metadata={
                "combined_results": len(candidates),
                "method_metadata": [item.metadata for item in candidates],
                "merge_policy": "list_without_semantic_merge",
            },
            evidence=tuple(ref for item in candidates for ref in item.evidence),
        )
