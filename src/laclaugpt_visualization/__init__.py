"""Standalone visualization and researcher-facing UI module for LaclauGPT."""

from .config import Settings, get_settings
from .data import load_frame, normalize_frame
from .plugins import (
    Permission,
    PluginAvailability,
    PluginCategory,
    PluginKind,
    PluginRegistry,
    default_registry,
)
from .products import DataProduct, EvidenceRef, ProductKind, ProductProvider
from .query_backends import (
    BackendUnavailable,
    ContextRequest,
    CsvQueryBackend,
    GraphRequest,
    MongoQueryBackend,
    ResearchQueryBackend,
    VectorCapability,
    graph_from_frame,
    resolve_query_backend,
)
from .services import (
    MongoRecordService,
    RedisConfigService,
    RedisMessageQueueService,
    RedisTaskQueueService,
    SQLiteNotesStore,
)

__all__ = [
    "BackendUnavailable",
    "ContextRequest",
    "CsvQueryBackend",
    "DataProduct",
    "EvidenceRef",
    "GraphRequest",
    "MongoQueryBackend",
    "MongoRecordService",
    "Permission",
    "PluginAvailability",
    "PluginCategory",
    "PluginKind",
    "PluginRegistry",
    "ProductKind",
    "ProductProvider",
    "RedisConfigService",
    "RedisMessageQueueService",
    "RedisTaskQueueService",
    "ResearchQueryBackend",
    "SQLiteNotesStore",
    "Settings",
    "VectorCapability",
    "default_registry",
    "get_settings",
    "graph_from_frame",
    "load_frame",
    "normalize_frame",
    "resolve_query_backend",
]
__version__ = "0.4.0"
