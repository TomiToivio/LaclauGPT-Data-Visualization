"""Failure-safe discovery and execution for optional plugin-driven pages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .plugins import PluginKind, PluginRegistry, RegisteredPlugin
from .products import ProductProvider


@dataclass(frozen=True, slots=True)
class PluginPage:
    """A plugin that is safe to expose as an optional visualization page."""

    plugin: RegisteredPlugin
    title: str


@dataclass(frozen=True, slots=True)
class PluginRenderResult:
    """Isolate renderer failures from the core dashboard."""

    ok: bool
    value: Any = None
    error: str | None = None


def discover_plugin_pages(
    registry: PluginRegistry,
    provider: ProductProvider,
    *,
    rag_enabled: bool = True,
    backend_capabilities: set[str] | frozenset[str] = frozenset(),
    fields: set[str] | frozenset[str] | None = None,
    mode: str | None = None,
) -> tuple[PluginPage, ...]:
    """Return only available, non-placeholder visualization plugins with renderers.

    Discovery is deliberately best-effort. A broken optional plugin cannot prevent
    Phase 0/core pages from starting.
    """
    pages: list[PluginPage] = []
    for plugin in registry.all(kind=PluginKind.VISUALIZATION):
        if plugin.render is None or plugin.spec.placeholder:
            continue
        try:
            status = registry.status(
                plugin.spec.name,
                provider,
                rag_enabled=rag_enabled,
                backend_capabilities=backend_capabilities,
                fields=fields,
                mode=mode,
            )
        except Exception:  # noqa: BLE001,S112 - optional plugin isolation boundary.
            continue
        if status.available:
            pages.append(PluginPage(plugin=plugin, title=plugin.spec.title or plugin.spec.name))
    return tuple(pages)


def render_plugin_page(
    registry: PluginRegistry,
    page: PluginPage,
    provider: ProductProvider,
    *,
    context: Mapping[str, Any] | None = None,
    project: str | None = None,
) -> PluginRenderResult:
    """Render one plugin without allowing it to take down the dashboard."""
    try:
        products = registry.load_products(page.plugin.spec.name, provider, project=project)
        if page.plugin.render is None:
            return PluginRenderResult(False, error="plugin renderer is unavailable")
        value = page.plugin.render(products, dict(context or {}))
        return PluginRenderResult(True, value=value)
    except Exception as exc:  # noqa: BLE001 - renderer isolation boundary.
        return PluginRenderResult(
            False,
            error=f"{type(exc).__name__}: {exc}",
        )
