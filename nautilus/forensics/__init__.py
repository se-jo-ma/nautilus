"""Nautilus forensics package (design §3.7).

Exposes :class:`ProcessedOffsets` (atomic on-disk tailer state with bounded
seen-hash LRU) and :class:`OffsetsCorruptError` (raised on malformed or
non-monotonic persisted state).
"""

from nautilus.forensics.offsets import (
    SEEN_HASH_CAP,
    OffsetsCorruptError,
    ProcessedOffsets,
)

__all__ = ["OffsetsCorruptError", "ProcessedOffsets", "SEEN_HASH_CAP"]
