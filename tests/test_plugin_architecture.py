from laclaugpt_visualization.plugins import Permission, PluginKind, default_registry
from laclaugpt_visualization.products import DataProduct, EvidenceRef, InMemoryProvider, ProductKind
from laclaugpt_visualization.workbench import ActionBroker, InMemoryAuditSink, Principal


def test_first_party_plugins_are_backend_neutral_and_capability_driven():
    provider = InMemoryProvider(
        {
            ProductKind.TABLE: DataProduct(ProductKind.TABLE, [{"x": 1}]),
            ProductKind.NETWORK: DataProduct(ProductKind.NETWORK, {"nodes": [], "edges": []}),
            ProductKind.GEODATA: DataProduct(ProductKind.GEODATA, {"type": "FeatureCollection", "features": []}),
            ProductKind.TIMELINE: DataProduct(ProductKind.TIMELINE, []),
            ProductKind.RECORDS: DataProduct(ProductKind.RECORDS, []),
        }
    )
    registry = default_registry()
    available = {plugin.spec.name for plugin in registry.available(provider, rag_enabled=False)}
    assert {"table", "map", "timeline", "network", "global_search"} <= available
    assert "rag_evidence" not in available
    assert all(plugin.spec.kind in PluginKind for plugin in registry.all())


def test_missing_capability_is_explicit():
    registry = default_registry()
    provider = InMemoryProvider({ProductKind.TABLE: DataProduct(ProductKind.TABLE, [])})
    try:
        registry.load_products("network", provider)
    except LookupError as exc:
        assert "network" in str(exc)
    else:
        raise AssertionError("missing capability must fail")


def test_evidence_is_preserved_on_logical_product():
    product = DataProduct(ProductKind.REPORT, "summary").with_evidence(
        [EvidenceRef("record-1", source_url="https://example.test/source")]
    )
    assert product.evidence[0].record_id == "record-1"


class FakeAnalysis:
    def status(self, project):
        return {"project": project}

    def run(self, project, *, record_ids=()):
        return f"job:{project}:{len(record_ids)}"

    def update_config(self, project, changes):
        return {"project": project, **changes}


def test_actions_require_permission_and_audit_agent_identity():
    audit = InMemoryAuditSink()
    broker = ActionBroker(audit=audit, analysis=FakeAnalysis())
    readonly = Principal("researcher")
    try:
        broker.run_analysis(readonly, "AI26")
    except PermissionError:
        pass
    else:
        raise AssertionError("read-only principal must not launch analysis")

    agent = Principal("agent-7", frozenset({Permission.RUN_ANALYSIS}), actor_type="agent")
    job_id = broker.run_analysis(agent, "AI26", record_ids=("r1", "r2"))
    assert job_id == "job:AI26:2"
    assert audit.events[-1].actor_type == "agent"
    assert audit.events[-1].project == "AI26"
