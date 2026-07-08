from __future__ import annotations

from typing import Any

import numpy as np

from state import AgentMemory, SymbolicState
from vision_dynamic_resnet import extract_dynamic_objects
from vision_interactive import extract_interactive_tiles
from vision_static_resnet import extract_static_tiles


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
        static = extract_static_tiles(obs)
        state.walls = static.walls
        state.floors = static.floors
        state.chests = static.chests
        state.exits = static.exits
        state.raw_features["static_vision_backend"] = static.backend
        state.raw_features["static_labels"] = static.labels
        state.raw_features["static_confidences"] = static.confidences
        dynamic = extract_dynamic_objects(obs)
        state.player = dynamic.player
        state.monsters = dynamic.monsters
        state.raw_features["dynamic_vision_backend"] = dynamic.backend
        state.raw_features["dynamic_objects"] = dynamic.objects
        state.raw_features["player_bbox"] = dynamic.player_bbox
        interactive = extract_interactive_tiles(obs)
        state.buttons = interactive.buttons
        state.switches = interactive.switches
        state.bridges = interactive.bridges
        state.gaps = interactive.gaps
        state.traps = interactive.traps
        if state.player is not None:
            state.buttons.discard(state.player)
            state.switches.discard(state.player)
        state.raw_features["interactive_vision_backend"] = interactive.backend

    return state


def tile_center_px(pos: tuple[int, int]) -> tuple[int, int]:
    x, y = pos
    return (x * TILE_SIZE + TILE_SIZE // 2, y * TILE_SIZE + TILE_SIZE // 2)


def pixel_to_tile(x: int, y: int) -> tuple[int, int]:
    return (x // TILE_SIZE, y // TILE_SIZE)
