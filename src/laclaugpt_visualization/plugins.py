"""Plugin registry and capability metadata for visualization and research UI extensions.

The public contract intentionally has only two top-level plugin kinds:

* ``visualization`` plugins are read-only representations of research products;
* ``user_interface`` plugins may edit state or enqueue work and therefore declare
  backend, permission, confirmation and audit requirements explicitly.

Older ``interaction`` / ``research_assistant`` names remain aliases for compatibility.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .products import DataProduct, ProductKind, ProductProvider


class PluginKind(StrEnum):
    VISUALIZATION = "visualization"
    USER_INTERFACE = "user_interface"

    # Compatibility aliases for the issue #22 foundation.
    INTERACTION = "user_interface"
    RESEARCH_ASSISTANT = "user_interface"


class PluginCategory(StrEnum):
    CORE = "core"
    TEMPORAL = "temporal"
    NETWORK = "network"
    GEOSPATIAL = "geospatial"
    MULTIMODAL = "multimodal"
    LEGACY = "legacy"
    RESEARCH_WORKFLOW = "research_workflow"
    DATA_MANAGEMENT = "data_management"
    CONFIGURATION = "configuration"
    TASKS = "tasks"
    CHAT_AGENT = "chat_agent"
    OPERATIONS = "operations"


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
    category: PluginCategory = PluginCategory.CORE
    title: str = ""
    description: str = ""
    orientation: str = "corpus"
    interactions: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    config_schema: Mapping[str, Any] = field(default_factory=dict)
    rag_required: bool = False
    required_fields: frozenset[str] = frozenset()
    optional_fields: frozenset[str] = frozenset()
    required_backends: frozenset[str] = frozenset()
    supported_modes: frozenset[str] = frozenset({"legacy_ep24", "canonical_live", "hybrid_research"})
    privacy: str = "research"
    mutates_state: bool = False
    confirmation_required: bool = False
    audit_required: bool = False
    placeholder: bool = False
    source: str | None = None

    @property
    def plugin_id(self) -> str:
        return self.name

    def __post_init__(self) -> None:
        if self.kind == PluginKind.VISUALIZATION and self.mutates_state:
            raise ValueError("visualization plugins must be read-only")
        if self.mutates_state and not self.audit_required:
            raise ValueError("state-changing UI plugins must require an audit trail")


RenderFn = Callable[[Mapping[ProductKind, DataProduct], Mapping[str, Any]], Any]


@dataclass(slots=True)
class RegisteredPlugin:
    spec: PluginSpec
    render: RenderFn | None = None


@dataclass(frozen=True, slots=True)
class PluginAvailability:
    available: bool
    missing_products: frozenset[ProductKind] = frozenset()
    missing_fields: frozenset[str] = frozenset()
    missing_backends: frozenset[str] = frozenset()
    mode_supported: bool = True
    rag_supported: bool = True

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.missing_products:
            reasons.append(
                "missing products: " + ", ".join(sorted(item.value for item in self.missing_products))
            )
        if self.missing_fields:
            reasons.append("missing fields: " + ", ".join(sorted(self.missing_fields)))
        if self.missing_backends:
            reasons.append("missing backends: " + ", ".join(sorted(self.missing_backends)))
        if not self.mode_supported:
            reasons.append("dashboard mode not supported")
        if not self.rag_supported:
            reasons.append("RAG capability disabled")
        return tuple(reasons)


class PluginRegistry:
    """Version-aware registry shared by read-only views and state-changing UI plugins."""

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

    def status(
        self,
        name: str,
        provider: ProductProvider,
        *,
        rag_enabled: bool = True,
        backend_capabilities: Iterable[str] = (),
        fields: Iterable[str] | None = None,
        mode: str | None = None,
    ) -> PluginAvailability:
        plugin = self.get(name)
        products = provider.capabilities()
        backends = set(backend_capabilities)
        known_fields = None if fields is None else set(fields)
        spec = plugin.spec
        missing_fields = (
            frozenset() if known_fields is None else frozenset(spec.required_fields - known_fields)
        )
        mode_supported = mode is None or mode in spec.supported_modes
        rag_supported = rag_enabled or not spec.rag_required
        missing_products = frozenset(spec.requires - products)
        missing_backends = frozenset(spec.required_backends - backends)
        return PluginAvailability(
            available=not (
                missing_products
                or missing_fields
                or missing_backends
                or not mode_supported
                or not rag_supported
            ),
            missing_products=missing_products,
            missing_fields=missing_fields,
            missing_backends=missing_backends,
            mode_supported=mode_supported,
            rag_supported=rag_supported,
        )

    def available(
        self,
        provider: ProductProvider,
        *,
        rag_enabled: bool = True,
        backend_capabilities: Iterable[str] = (),
        fields: Iterable[str] | None = None,
        mode: str | None = None,
        include_placeholders: bool = True,
    ) -> tuple[RegisteredPlugin, ...]:
        return tuple(
            plugin
            for plugin in self.all()
            if (include_placeholders or not plugin.spec.placeholder)
            and self.status(
                plugin.spec.name,
                provider,
                rag_enabled=rag_enabled,
                backend_capabilities=backend_capabilities,
                fields=fields,
                mode=mode,
            ).available
        )

    def load_products(
        self, name: str, provider: ProductProvider, *, project: str | None = None
    ) -> dict[ProductKind, DataProduct]:
        plugin = self.get(name)
        missing = plugin.spec.requires - provider.capabilities()
        if missing:
            names = ", ".join(sorted(kind.value for kind in missing))
            raise LookupError(f"plugin {name!r} is missing capabilities: {names}")
        return {kind: provider.get_product(kind, project=project) for kind in plugin.spec.requires}


def _plugin(
    name: str,
    title: str,
    kind: PluginKind,
    category: PluginCategory,
    *,
    requires: Iterable[ProductKind] = (),
    fields: Iterable[str] = (),
    optional_fields: Iterable[str] = (),
    backends: Iterable[str] = (),
    permissions: Iterable[Permission] = (Permission.VIEW,),
    interactions: Iterable[str] = (),
    exports: Iterable[str] = (),
    orientation: str = "corpus",
    mutates: bool = False,
    confirmation: bool = False,
    audit: bool = False,
    rag: bool = False,
    placeholder: bool = False,
    source: str | None = None,
    modes: Iterable[str] = ("legacy_ep24", "canonical_live", "hybrid_research"),
) -> RegisteredPlugin:
    return RegisteredPlugin(
        PluginSpec(
            name=name,
            version="1.0",
            kind=kind,
            category=category,
            title=title,
            description=title,
            requires=frozenset(requires),
            required_fields=frozenset(fields),
            optional_fields=frozenset(optional_fields),
            required_backends=frozenset(backends),
            permissions=frozenset(permissions),
            interactions=tuple(interactions),
            exports=tuple(exports),
            orientation=orientation,
            mutates_state=mutates,
            confirmation_required=confirmation,
            audit_required=audit,
            rag_required=rag,
            placeholder=placeholder,
            source=source,
            supported_modes=frozenset(modes),
        )
    )


def first_party_plugins() -> tuple[RegisteredPlugin, ...]:
    """Catalog of maintained, legacy-adapted and planned dashboard components."""

    v = PluginKind.VISUALIZATION
    ui = PluginKind.USER_INTERFACE
    return (
        # Core read-only research representations.
        _plugin("table", "Research dataframe", v, PluginCategory.CORE, requires=(ProductKind.TABLE,), interactions=("search", "filter", "paginate", "select_columns"), exports=("csv", "parquet"), source="current app.py / legacy EP24 table"),
        _plugin("record_evidence", "Record and evidence viewer", v, PluginCategory.CORE, requires=(ProductKind.RECORDS,), fields=("source_url",), optional_fields=("transcript", "ocr", "frames", "provenance"), interactions=("select_record", "open_source"), source="current Researcher Review + legacy EP24"),
        _plugin("corpus_monitor", "Corpus monitor", v, PluginCategory.CORE, requires=(ProductKind.TABLE,), interactions=("filter",), source="current Monitor"),
        _plugin("distributions", "Distribution charts", v, PluginCategory.CORE, requires=(ProductKind.TABLE,), interactions=("filter", "drilldown"), exports=("csv", "png"), source="current Monitor/Explore + legacy EP24 charts"),
        _plugin("crosstab_heatmap", "Cross-tab and heatmap", v, PluginCategory.CORE, requires=(ProductKind.TABLE,), interactions=("select_dimensions", "filter"), exports=("csv", "png"), placeholder=True),
        _plugin("data_quality", "Data-quality and schema diagnostics", v, PluginCategory.CORE, requires=(ProductKind.TABLE,), interactions=("filter", "open_record"), exports=("csv",), placeholder=True),
        # Time/change.
        _plugin("timeline", "Multi-clock timeline", v, PluginCategory.TEMPORAL, requires=(ProductKind.TIMELINE,), orientation="time", interactions=("time_window", "drilldown"), exports=("csv",), source="research_views.timeline_counts"),
        _plugin("trends", "Trend and delta view", v, PluginCategory.TEMPORAL, requires=(ProductKind.TIMELINE, ProductKind.TABLE), interactions=("metric", "time_window"), placeholder=True),
        _plugin("reports", "Daily and research reports", v, PluginCategory.TEMPORAL, requires=(ProductKind.REPORT,), interactions=("select_report", "inspect_evidence"), exports=("markdown", "json"), source="current Reports"),
        _plugin("temporal_compare", "Temporal comparison", v, PluginCategory.TEMPORAL, requires=(ProductKind.TABLE,), interactions=("select_windows", "metric"), placeholder=True),
        # Graph/discourse views. These display precomputed analytical objects only.
        _plugin("network", "Generic relation/network graph", v, PluginCategory.NETWORK, requires=(ProductKind.NETWORK,), orientation="graph", interactions=("zoom", "pan", "edge_filter", "community_filter", "evidence_drilldown"), exports=("graphml", "json"), source="transforms.graph_projection"),
        _plugin("discourse_graph", "Discourse graph", v, PluginCategory.NETWORK, requires=(ProductKind.KNOWLEDGE_GRAPH,), interactions=("select_node", "select_relation", "inspect_evidence"), placeholder=True),
        _plugin("actor_network", "Actor/entity SNA network", v, PluginCategory.NETWORK, requires=(ProductKind.NETWORK,), orientation="graph", interactions=("zoom", "pan", "edge_filter", "evidence_drilldown"), exports=("json",), source="sna.sna_envelope (explicit upstream NETWORK product only)"),
        _plugin("bipartite_network", "Bipartite/multiplex projection", v, PluginCategory.NETWORK, requires=(ProductKind.NETWORK,), placeholder=True),
        _plugin("graph_delta", "Graph-over-time delta", v, PluginCategory.NETWORK, requires=(ProductKind.NETWORK, ProductKind.TIMELINE), placeholder=True),
        _plugin("sankey", "Alluvial/Sankey articulation view", v, PluginCategory.NETWORK, requires=(ProductKind.TABLE,), placeholder=True),
        _plugin("embedding", "Embedding / social-space view", v, PluginCategory.NETWORK, requires=(ProductKind.TABLE,), optional_fields=("embedding_x", "embedding_y"), placeholder=True),
        # Space and multimodal evidence.
        _plugin("map", "Provenance-aware map", v, PluginCategory.GEOSPATIAL, requires=(ProductKind.GEODATA,), orientation="map", interactions=("time_filter", "cluster", "evidence_drilldown"), exports=("geojson",), source="research_views.map_points"),
        _plugin("map_timeline", "Map + timeline", v, PluginCategory.GEOSPATIAL, requires=(ProductKind.GEODATA, ProductKind.TIMELINE), placeholder=True),
        _plugin("media_gallery", "Media gallery", v, PluginCategory.MULTIMODAL, requires=(ProductKind.MEDIA,), interactions=("open_record",), placeholder=True),
        _plugin("multimodal_evidence", "Transcript/OCR/frame evidence", v, PluginCategory.MULTIMODAL, requires=(ProductKind.RECORDS,), optional_fields=("transcript", "whisper_transcript", "ocr", "frames", "frame_analysis"), source="current Researcher Review + legacy EP24"),
        # Legacy/special datasets stay isolated from the canonical pipeline.
        _plugin("legacy_ep24", "EP24 legacy research views", v, PluginCategory.LEGACY, requires=(ProductKind.TABLE,), modes=("legacy_ep24", "hybrid_research"), source="legacy_ep24.py + ep2024_postprocess/dashboard/dashboard.py"),
        _plugin("legacy_art", "EP24 orbital data-art view", v, PluginCategory.LEGACY, requires=(ProductKind.TABLE,), modes=("legacy_ep24", "hybrid_research"), placeholder=True, source="KEEP_PRIVATE/experimental/legacy_art_visualization"),
        _plugin("pledge_dashboard", "Legacy pledge dashboard", v, PluginCategory.LEGACY, requires=(ProductKind.TABLE,), fields=("source_url",), interactions=("filter", "inspect_evidence"), source="pledge_dashboard.py"),
        # Research/UI plugins. Mutations always declare permissions and audit requirements.
        _plugin("global_search", "Global search", ui, PluginCategory.RESEARCH_WORKFLOW, requires=(ProductKind.RECORDS,), interactions=("full_text", "filter", "open_record")),
        _plugin("researcher_review", "Researcher review and annotation", ui, PluginCategory.RESEARCH_WORKFLOW, requires=(ProductKind.RECORDS,), permissions=(Permission.VIEW, Permission.ANNOTATE), interactions=("review", "correct", "request_rerun"), mutates=True, audit=True, source="current review.py / Researcher Review"),
        _plugin("ethnography_notes", "Digital ethnography notebook", ui, PluginCategory.RESEARCH_WORKFLOW, permissions=(Permission.VIEW, Permission.ANNOTATE), interactions=("create_note", "link_evidence", "tag"), mutates=True, audit=True),
        _plugin("research_notes", "Research notes", ui, PluginCategory.RESEARCH_WORKFLOW, permissions=(Permission.VIEW, Permission.ANNOTATE), interactions=("create_note", "link_record"), mutates=True, audit=True),
        _plugin("codebook_editor", "Codebook editor", ui, PluginCategory.RESEARCH_WORKFLOW, backends=("redis_config",), permissions=(Permission.VIEW, Permission.EDIT_ANALYSIS_CONFIG), mutates=True, confirmation=True, audit=True, placeholder=True),
        _plugin("config_inspector", "Prompt/config inspector", ui, PluginCategory.CONFIGURATION, interactions=("inspect", "diff")),
        _plugin("mongodb_editor", "MongoDB record editor", ui, PluginCategory.DATA_MANAGEMENT, requires=(ProductKind.RECORDS,), backends=("mongodb",), permissions=(Permission.VIEW, Permission.EDIT_DERIVED), mutates=True, confirmation=True, audit=True),
        _plugin("record_quarantine", "Soft-delete / quarantine record", ui, PluginCategory.DATA_MANAGEMENT, requires=(ProductKind.RECORDS,), backends=("mongodb",), permissions=(Permission.VIEW, Permission.EXCLUDE), mutates=True, confirmation=True, audit=True),
        _plugin("bulk_edit", "Bulk edit/tag/review", ui, PluginCategory.DATA_MANAGEMENT, requires=(ProductKind.RECORDS,), backends=("mongodb",), permissions=(Permission.VIEW, Permission.EDIT_DERIVED), mutates=True, confirmation=True, audit=True, placeholder=True),
        _plugin("export_snapshot", "Export / snapshot", ui, PluginCategory.DATA_MANAGEMENT, requires=(ProductKind.TABLE,), permissions=(Permission.VIEW, Permission.EXPORT), interactions=("preview", "export"), exports=("csv", "jsonl", "parquet")),
        _plugin("distributed_settings", "Distributed study/module settings", ui, PluginCategory.CONFIGURATION, backends=("redis_config",), permissions=(Permission.VIEW, Permission.EDIT_COLLECTION_CONFIG, Permission.EDIT_ANALYSIS_CONFIG), mutates=True, confirmation=True, audit=True),
        _plugin("task_launcher", "Task launcher", ui, PluginCategory.TASKS, backends=("redis_task_queue",), permissions=(Permission.VIEW, Permission.RUN_ANALYSIS), interactions=("preview_targets", "enqueue"), mutates=True, confirmation=True, audit=True),
        _plugin("task_monitor", "Task/queue monitor", ui, PluginCategory.TASKS, backends=("redis_task_queue",), interactions=("refresh", "inspect_job")),
        _plugin("url_ingest", "URL/source ingestion", ui, PluginCategory.TASKS, backends=("redis_task_queue",), permissions=(Permission.VIEW, Permission.RUN_COLLECTION), mutates=True, confirmation=True, audit=True),
        _plugin("batch_reprocess", "Batch reprocessing", ui, PluginCategory.TASKS, requires=(ProductKind.RECORDS,), backends=("redis_task_queue",), permissions=(Permission.VIEW, Permission.RUN_ANALYSIS), interactions=("preview_targets", "enqueue"), mutates=True, confirmation=True, audit=True),
        _plugin("rag_chat", "LaclauGPT RAG chat", ui, PluginCategory.CHAT_AGENT, requires=(ProductKind.RETRIEVAL,), backends=("redis_message_queue",), interactions=("ask", "inspect_evidence", "attach_dashboard_context"), rag=True),
        _plugin("rag_evidence", "RAG evidence viewer", ui, PluginCategory.CHAT_AGENT, requires=(ProductKind.RETRIEVAL,), interactions=("inspect_evidence", "inspect_retrieval"), rag=True),
        _plugin("agent_console", "Agent console", ui, PluginCategory.CHAT_AGENT, backends=("redis_message_queue", "redis_task_queue"), permissions=(Permission.VIEW, Permission.RUN_ANALYSIS), interactions=("submit_task", "inspect_progress"), mutates=True, confirmation=True, audit=True, placeholder=True),
        _plugin("backend_status", "Backend health/status", ui, PluginCategory.OPERATIONS, interactions=("refresh",)),
        _plugin("plugin_manager", "Plugin manager", ui, PluginCategory.OPERATIONS, interactions=("inspect_availability",)),
    )


def default_registry() -> PluginRegistry:
    registry = PluginRegistry()
    for plugin in first_party_plugins():
        registry.register(plugin)
    return registry
