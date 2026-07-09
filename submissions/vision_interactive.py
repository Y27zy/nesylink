from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .state import Position
from .vision_static_resnet import ROOM_HEIGHT_TILES, ROOM_WIDTH_TILES, TILE_SIZE, color_mask


BRIDGE_WOOD = (172, 104, 48)
BRIDGE_EDGE = (96, 48, 26)
GAP_DARK = (16, 22, 48)
BUTTON_UP = (40, 190, 74)
BUTTON_DOWN = (28, 112, 52)
SWITCH_BODY = (255, 216, 80)
SWITCH_DOWN = (184, 124, 42)
FLOOR_LIGHT = (72, 122, 248)
CHEST_WOOD = (152, 82, 36)
DOOR_WOOD = (96, 48, 26)
SPIKE_METAL = (238, 238, 236)
SPIKE_SHADE = (112, 112, 126)


@dataclass(frozen=True)
class InteractiveVisionResult:
    buttons: set[Position]
    switches: set[Position]
    bridges: set[Position]
    gaps: set[Position]
    traps: set[Position]
    backend: str


def extract_interactive_tiles(obs: np.ndarray) -> InteractiveVisionResult:
    buttons: set[Position] = set()
    switches: set[Position] = set()
    bridges: set[Position] = set()
    gaps: set[Position] = set()
    traps: set[Position] = set()

    for y in range(ROOM_HEIGHT_TILES):
        for x in range(ROOM_WIDTH_TILES):
            tile = obs[
                y * TILE_SIZE : (y + 1) * TILE_SIZE,
                x * TILE_SIZE : (x + 1) * TILE_SIZE,
            ]
            pos = (x, y)
            if _is_bridge_tile(tile):
                bridges.add(pos)
            elif _is_button_tile(tile):
                buttons.add(pos)
            elif _is_switch_tile(tile, pos):
                switches.add(pos)
            elif _is_abyss_tile(tile):
                gaps.add(pos)
                traps.add(pos)
            elif _is_gap_tile(tile):
                gaps.add(pos)
            elif _is_spike_tile(tile):
                traps.add(pos)

    return InteractiveVisionResult(
        buttons=buttons,
        switches=switches,
        bridges=bridges,
        gaps=gaps,
        traps=traps,
        backend="colors",
    )


def _is_bridge_tile(tile: np.ndarray) -> bool:
    wood = int(color_mask(tile, BRIDGE_WOOD, tolerance=18).sum())
    edge = int(color_mask(tile, BRIDGE_EDGE, tolerance=18).sum())
    # The player or an exit may partially cover a bridge.
    return wood >= 14 and edge >= 12


def _is_button_tile(tile: np.ndarray) -> bool:
    lower = tile[TILE_SIZE // 2 :, :, :]
    lower_up = int(color_mask(lower, BUTTON_UP, tolerance=20).sum())
    lower_down = int(color_mask(lower, BUTTON_DOWN, tolerance=20).sum())
    outline = int((lower.max(axis=-1) <= 20).sum())
    return (lower_up >= 12 or lower_down >= 12) and outline >= 34


def _is_switch_tile(tile: np.ndarray, pos: Position) -> bool:
    x, y = pos
    if x in {0, ROOM_WIDTH_TILES - 1} or y in {0, ROOM_HEIGHT_TILES - 1}:
        return False

    body = int(color_mask(tile, SWITCH_BODY, tolerance=18).sum())
    down = int(color_mask(tile, SWITCH_DOWN, tolerance=18).sum())
    chest_wood = int(color_mask(tile, CHEST_WOOD, tolerance=18).sum())
    door_wood = int(color_mask(tile, DOOR_WOOD, tolerance=18).sum())
    if chest_wood >= 12 or door_wood >= 12:
        return False

    top_body = int(color_mask(tile[1:6], SWITCH_BODY, tolerance=18).sum())
    lower_body = int(color_mask(tile[7:12], SWITCH_BODY, tolerance=18).sum())
    lower_down = int(color_mask(tile[7:12], SWITCH_DOWN, tolerance=18).sum())
    return (
        (body >= 18 or down >= 18)
        and top_body >= 2
        and (lower_body >= 12 or lower_down >= 12 or down >= 12)
    )


def _is_abyss_tile(tile: np.ndarray) -> bool:
    black = int((tile.max(axis=-1) <= 8).sum())
    return black > TILE_SIZE * TILE_SIZE * 0.85


def _is_gap_tile(tile: np.ndarray) -> bool:
    gap_dark = int(color_mask(tile, GAP_DARK, tolerance=12).sum())
    floor_light = int(color_mask(tile, FLOOR_LIGHT, tolerance=14).sum())
    return gap_dark > 80 and floor_light < 20


def _is_spike_tile(tile: np.ndarray) -> bool:
    metal = int(color_mask(tile, SPIKE_METAL, tolerance=14).sum())
    shade = int(color_mask(tile, SPIKE_SHADE, tolerance=14).sum())
    return metal >= 8 and shade >= 6
