from laclaugpt_visualization.plugin_pages import (
    discover_plugin_pages,
    render_plugin_page,
)
from laclaugpt_visualization.plugins import (
    PluginKind,
    PluginRegistry,
    PluginSpec,
    RegisteredPlugin,
)
from laclaugpt_visualization.products import DataProduct, InMemoryProvider, ProductKind


def _plugin(name="synthetic", render=None, *, requires=(ProductKind.TABLE,)):
    return RegisteredPlugin(
        PluginSpec(
            name=name,
            version="1.0",
            kind=PluginKind.VISUALIZATION,
            title="Synthetic plugin",
            requires=frozenset(requires),
        ),
        render=render,
    )


def test_no_plugin_startup_has_no_optional_pages():
    registry = PluginRegistry()
    provider = InMemoryProvider({ProductKind.TABLE: DataProduct(ProductKind.TABLE, [])})
    assert discover_plugin_pages(registry, provider) == ()


def test_synthetic_plugin_is_visible_when_contract_matches():
    registry = PluginRegistry()
    registry.register(_plugin(render=lambda products, context: "ok"))
    provider = InMemoryProvider({ProductKind.TABLE: DataProduct(ProductKind.TABLE, [{"x": 1}])})
    pages = discover_plugin_pages(registry, provider, fields={"x"}, mode="canonical_live")
    assert [page.plugin.spec.name for page in pages] == ["synthetic"]


def test_plugin_with_missing_product_is_not_visible():
    registry = PluginRegistry()
    registry.register(
        _plugin(
            render=lambda products, context: "never",
            requires=(ProductKind.NETWORK,),
        )
    )
    provider = InMemoryProvider({ProductKind.TABLE: DataProduct(ProductKind.TABLE, [])})
    assert discover_plugin_pages(registry, provider) == ()


def test_plugin_failure_is_isolated():
    def explode(products, context):
        raise RuntimeError("boom")

    registry = PluginRegistry()
    registry.register(_plugin(render=explode))
    provider = InMemoryProvider({ProductKind.TABLE: DataProduct(ProductKind.TABLE, [])})
    page = discover_plugin_pages(registry, provider)[0]
    result = render_plugin_page(registry, page, provider)
    assert result.ok is False
    assert "RuntimeError: boom" == result.error


def test_core_provider_remains_usable_after_plugin_failure():
    def explode(products, context):
        raise RuntimeError("boom")

    registry = PluginRegistry()
    registry.register(_plugin(render=explode))
    product = DataProduct(ProductKind.TABLE, [{"source_url": "https://example.test/1"}])
    provider = InMemoryProvider({ProductKind.TABLE: product})
    page = discover_plugin_pages(registry, provider)[0]
    assert render_plugin_page(registry, page, provider).ok is False
    assert provider.get_product(ProductKind.TABLE).payload == product.payload
