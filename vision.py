from __future__ import annotations

from typing import Any

import numpy as np

from state import AgentMemory, SymbolicState


TILE_SIZE = 16
ROOM_WIDTH_TILES = 10
ROOM_HEIGHT_TILES = 8


def extract_symbolic_state(
    obs: Any,
    memory: AgentMemory,
    *,
    inventory: dict[str, Any] | None = None,
) -> SymbolicState:
    """Convert raw pixel observation into a tile-level symbolic state.

    This placeholder only fills inventory-like public fields. Team members B/C
    should add pixel classifiers here. Hidden info fields must not be used in
    this function during final inference.
    """

    memory.step_count += 1
    inv = inventory or {}
    state = SymbolicState(
        keys=int(inv.get("keys", 0) or 0),
        gold=int(inv.get("gold", 0) or 0),
        items=tuple(str(item) for item in inv.get("items", ()) or ()),
        tools=tuple(str(item) for item in inv.get("tools", ()) or ()),
        equipped=dict(inv.get("equipped", {}) or {}),
    )

    if isinstance(obs, np.ndarray):
        state.raw_features["obs_shape"] = tuple(obs.shape)
        state.raw_features["obs_dtype"] = str(obs.dtype)

    return state


def tile_center_px(pos: tuple[int, int]) -> tuple[int, int]:
    x, y = pos
    return (x * TILE_SIZE + TILE_SIZE // 2, y * TILE_SIZE + TILE_SIZE // 2)


def pixel_to_tile(x: int, y: int) -> tuple[int, int]:
    return (x // TILE_SIZE, y // TILE_SIZE)

