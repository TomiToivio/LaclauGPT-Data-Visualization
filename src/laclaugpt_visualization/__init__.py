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
from .services import (
    MongoRecordService,
    RedisConfigService,
    RedisMessageQueueService,
    RedisTaskQueueService,
    SQLiteNotesStore,
)

__all__ = [
    "DataProduct",
    "EvidenceRef",
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
    "SQLiteNotesStore",
    "Settings",
    "default_registry",
    "get_settings",
    "load_frame",
    "normalize_frame",
]
__version__ = "0.3.0"
