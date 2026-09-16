"""Standalone visualization and researcher-facing UI module for LaclauGPT."""

from .config import Settings, get_settings
from .data import load_frame, normalize_frame
from .plugins import Permission, PluginKind, PluginRegistry, default_registry
from .products import DataProduct, EvidenceRef, ProductKind, ProductProvider

__all__ = [
    "DataProduct",
    "EvidenceRef",
    "Permission",
    "PluginKind",
    "PluginRegistry",
    "ProductKind",
    "ProductProvider",
    "Settings",
    "default_registry",
    "get_settings",
    "load_frame",
    "normalize_frame",
]
__version__ = "0.2.0"
