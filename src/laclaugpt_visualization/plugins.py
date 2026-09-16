"""Plugin registry and capability metadata for visualization and research UI extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping

from .products import DataProduct, ProductKind, ProductProvider


class PluginKind(StrEnum):
    VISUALIZATION = "visualization"
    INTERACTION = "interaction"
    RESEARCH_ASSISTANT = "research_assistant"


class Permission(StrEnum):
    VIEW = "view"
    ANNOTATE = "annotate"
    EDIT_DERIVED = "edit_derived_data"
    EDIT_COLLECTION_CONFIG = "edit_collection_config"
    EDIT_ANALYSIS_CONFIG = "edit_analysis_config"
    RUN_COLLECTION = "run_collection"
    RUN_ANALYSIS = "run_analysis"
    EXPORT = "export"
    EXCLUDE = "soft_delete_exclude"
    PHYSICAL_DELETE = "physical_delete"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class PluginSpec:
    name: str
    version: str
    kind: PluginKind
    requires: frozenset[ProductKind] = frozenset()
    permissions: frozenset[Permission] = frozenset({Permission.VIEW})
    orientation: str = "corpus"
    interactions: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    config_schema: Mapping[str, Any] = field(default_factory=dict)
    rag_required: bool = False


RenderFn = Callable[[Mapping[ProductKind, DataProduct], Mapping[str, Any]], Any]


@dataclass(slots=True)
class RegisteredPlugin:
    spec: PluginSpec
    render: RenderFn | None = None


class PluginRegistry:
    """Version-aware registry shared by visualization, UI, and assistant plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, RegisteredPlugin] = {}

    def register(self, plugin: RegisteredPlugin, *, replace: bool = False) -> None:
        existing = self._plugins.get(plugin.spec.name)
        if existing is not None and not replace:
            raise ValueError(f"plugin already registered: {plugin.spec.name}")
        self._plugins[plugin.spec.name] = plugin

    def get(self, name: str) -> RegisteredPlugin:
        return self._plugins[name]

    def all(self, *, kind: PluginKind | None = None) -> tuple[RegisteredPlugin, ...]:
        values = self._plugins.values()
        if kind is not None:
            values = (plugin for plugin in values if plugin.spec.kind == kind)
        return tuple(sorted(values, key=lambda plugin: plugin.spec.name))

    def available(self, provider: ProductProvider, *, rag_enabled: bool = True) -> tuple[RegisteredPlugin, ...]:
        capabilities = provider.capabilities()
        return tuple(
            plugin
            for plugin in self.all()
            if plugin.spec.requires <= capabilities and (rag_enabled or not plugin.spec.rag_required)
        )

    def load_products(self, name: str, provider: ProductProvider, *, project: str | None = None) -> dict[ProductKind, DataProduct]:
        plugin = self.get(name)
        missing = plugin.spec.requires - provider.capabilities()
        if missing:
            names = ", ".join(sorted(kind.value for kind in missing))
            raise LookupError(f"plugin {name!r} is missing capabilities: {names}")
        return {kind: provider.get_product(kind, project=project) for kind in plugin.spec.requires}


def first_party_plugins() -> tuple[RegisteredPlugin, ...]:
    """Backend-neutral descriptors for the first independent visualization plugins."""

    common = {"search", "filter", "evidence_drilldown"}
    specs: Iterable[PluginSpec] = (
        PluginSpec("table", "1.0", PluginKind.VISUALIZATION, frozenset({ProductKind.TABLE}), interactions=tuple(sorted(common | {"paginate", "select_columns"})), exports=("csv", "parquet")),
        PluginSpec("map", "1.0", PluginKind.VISUALIZATION, frozenset({ProductKind.GEODATA}), orientation="map", interactions=tuple(sorted(common | {"time_filter", "cluster"})), exports=("geojson",)),
        PluginSpec("timeline", "1.0", PluginKind.VISUALIZATION, frozenset({ProductKind.TIMELINE}), orientation="time", interactions=tuple(sorted(common | {"time_window"})), exports=("csv",)),
        PluginSpec("network", "1.0", PluginKind.VISUALIZATION, frozenset({ProductKind.NETWORK}), orientation="graph", interactions=tuple(sorted(common | {"zoom", "pan", "edge_filter", "community_filter"})), exports=("graphml", "json")),
        PluginSpec("rag_evidence", "1.0", PluginKind.RESEARCH_ASSISTANT, frozenset({ProductKind.RETRIEVAL}), interactions=("ask", "inspect_evidence", "inspect_retrieval"), rag_required=True),
        PluginSpec("global_search", "1.0", PluginKind.INTERACTION, frozenset({ProductKind.RECORDS}), interactions=("full_text", "filter", "open_record")),
    )
    return tuple(RegisteredPlugin(spec) for spec in specs)


def default_registry() -> PluginRegistry:
    registry = PluginRegistry()
    for plugin in first_party_plugins():
        registry.register(plugin)
    return registry
