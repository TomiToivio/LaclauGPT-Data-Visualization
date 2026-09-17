"""RDF plugin registrations kept separate from the core registry.

RDF plugins are added only when project policy enables RDF. Runtime endpoint settings alone
never register them, which prevents machine configuration from overriding project policy.
"""
from __future__ import annotations

from .plugins import (
    Permission,
    PluginCategory,
    PluginKind,
    PluginRegistry,
    PluginSpec,
    RegisteredPlugin,
)
from .rdf import RDFProjectPolicy


def _rdf_plugin(
    name: str,
    title: str,
    *,
    backends: frozenset[str],
    interactions: tuple[str, ...],
    exports: tuple[str, ...] = (),
    permissions: frozenset[Permission] = frozenset({Permission.VIEW}),
    rag_required: bool = False,
) -> RegisteredPlugin:
    return RegisteredPlugin(
        PluginSpec(
            name=name,
            version="1.0",
            kind=PluginKind.VISUALIZATION,
            category=PluginCategory.NETWORK,
            title=title,
            description=title,
            orientation="graph",
            required_backends=backends,
            permissions=permissions,
            interactions=interactions,
            exports=exports,
            rag_required=rag_required,
            source="issue #31 RDF/Linked Data visualization",
        )
    )


def register_rdf_plugins(
    registry: PluginRegistry,
    policy: RDFProjectPolicy,
    *,
    provider_available: bool,
) -> PluginRegistry:
    """Register RDF plugins iff the project explicitly enables RDF.

    ``provider_available`` affects capability metadata, not project policy. The caller can
    advertise the ``rdf_provider`` backend only when a usable provider/export service exists.
    """
    if not policy.enabled:
        return registry

    backend = frozenset({"rdf_provider"})
    registry.register(
        _rdf_plugin(
            "rdf_graph_explorer",
            "RDF knowledge-graph explorer",
            backends=backend,
            interactions=(
                "semantic_filter",
                "named_graph_filter",
                "neighbor_expand",
                "describe_resource",
                "graph_table_switch",
                "evidence_drilldown",
            ),
            exports=("json-ld", "turtle", "n-quads", "n-triples", "trig", "rdf-xml"),
        )
    )
    registry.register(
        _rdf_plugin(
            "rdf_query",
            "Read-only SPARQL/query explorer",
            backends=backend,
            interactions=("predefined_query", "read_only_sparql", "inspect_query_provenance"),
        )
    )
    registry.register(
        _rdf_plugin(
            "rdf_export",
            "Analysis-owned RDF export controls",
            backends=backend,
            interactions=("select_scope", "request_export"),
            exports=("json-ld", "turtle", "n-quads", "n-triples", "trig", "rdf-xml"),
            permissions=frozenset({Permission.VIEW, Permission.EXPORT}),
        )
    )
    if policy.graphrag_enabled:
        registry.register(
            _rdf_plugin(
                "rdf_graphrag_context",
                "RDF GraphRAG context inspector",
                backends=backend,
                interactions=("inspect_context", "inspect_paths", "inspect_sources"),
            )
        )

    # ``provider_available`` is intentionally not used to suppress registration: enabled
    # projects should show a graceful unavailable status when the service is absent.
    _ = provider_available
    return registry
