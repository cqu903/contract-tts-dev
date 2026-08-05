"""Compatibility exports for contract storage and segment indexing."""

from backend.storage.contract import (
    ContractStore,
    SegmentIndex,
    build_index,
    compute_contract_id,
    dump_segments,
    position_to_segment,
)

__all__ = [
    "ContractStore",
    "SegmentIndex",
    "build_index",
    "compute_contract_id",
    "dump_segments",
    "position_to_segment",
]
