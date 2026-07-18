from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nesylink.core.constants import (
    COLOR_EXIT_CONDITIONAL,
    COLOR_EXIT_LOCKED,
    COLOR_EXIT_NORMAL,
    COLOR_MONSTER_AMBUSHER,
    COLOR_MONSTER_CHASER,
    COLOR_MONSTER_PATROLLER,
    COLOR_NPC,
)
from nesylink.core.rendering.sprites import (
    draw_abyss,
    draw_bridge,
    draw_button,
    draw_chest,
    draw_exit,
    draw_floor,
    draw_gap,
    draw_monster,
    draw_npc,
    draw_player_shield,
    draw_player_sprite,
    draw_player_sword,
    draw_switch,
    draw_trap,
    draw_wall,
)

from submissions.vision_dynamic_resnet import (
    DYNAMIC_CLASS_TO_INDEX,
    FACING_NAMES,
    OUTPUT_STRIDE,
)
from submissions.vision_preprocess import (
    COLOR_VARIANTS,
    apply_color_variant,
    robust_channels,
    robust_frame_channels,
)
from submissions.vision_static_resnet import (
    CHEST_NAMES,
    EXIT_NAMES,
    OBJECT_NAMES,
    STATE_NAMES,
    TERRAIN_NAMES,
    TILE_SIZE,
)


MAP_HEIGHT = 128
MAP_WIDTH = 160
HEATMAP_HEIGHT = MAP_HEIGHT // OUTPUT_STRIDE
HEATMAP_WIDTH = MAP_WIDTH // OUTPUT_STRIDE

MONSTER_RENDER_INFO = {
    "monster_chaser": ("chaser", COLOR_MONSTER_CHASER),
    "monster_patroller": ("patroller", COLOR_MONSTER_PATROLLER),
    "monster_ambusher": ("ambusher", COLOR_MONSTER_AMBUSHER),
}


@dataclass(frozen=True)
class StaticTargets:
    terrain: int
    object: int
    chest: int
    exit: int
    state: int
    state_relevant: bool


STATIC_SYMBOLS = (
    "floor",
    "wall",
    "trap_spike",
    "trap_abyss",
    "gap",
    "bridge",
    "chest_key_closed",
    "chest_key_open",
    "chest_gold_closed",
    "chest_gold_open",
    "chest_heal_closed",
    "chest_heal_open",
    "chest_item_closed",
    "chest_item_open",
    "npc",
    "button_default",
    "button_changed",
    "switch_default",
    "switch_changed",
    "exit_normal_default",
    "exit_locked_key_default",
    "exit_locked_key_changed",
    "exit_conditional_default",
)


def generate_static_batch(batch_size: int, seed: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    images: list[np.ndarray] = []
    targets: list[StaticTargets] = []
    for index in range(batch_size):
        rng = np.random.default_rng(seed + index * 104729)
        symbol = STATIC_SYMBOLS[(seed + index) % len(STATIC_SYMBOLS)]
        image, target = render_static_sample(rng, symbol)
        variant = COLOR_VARIANTS[(seed // 7 + index) % len(COLOR_VARIANTS)]
        images.append(apply_color_variant(image, variant))
        targets.append(target)
    arrays = {
        "terrain": np.asarray([target.terrain for target in targets], dtype=np.int64),
        "object": np.asarray([target.object for target in targets], dtype=np.int64),
        "chest": np.asarray([target.chest for target in targets], dtype=np.int64),
        "exit": np.asarray([target.exit for target in targets], dtype=np.int64),
        "state": np.asarray([target.state for target in targets], dtype=np.int64),
        "state_relevant": np.asarray(
            [target.state_relevant for target in targets], dtype=np.bool_
        ),
    }
    return robust_channels(np.stack(images)), arrays


def render_static_sample(
    rng: np.random.Generator,
    symbol: str,
) -> tuple[np.ndarray, StaticTargets]:
    frame = np.zeros((TILE_SIZE * 3, TILE_SIZE * 3, 3), dtype=np.uint8)
    for row in range(3):
        for col in range(3):
            draw_floor(frame, col, row)
    center = (1, 1)

    terrain = "floor"
    obj = "none"
    chest = "none"
    exit_kind = "none"
    changed = False
    state_relevant = False

    if symbol == "wall":
        terrain = "wall"
        draw_wall(frame, *center)
    elif symbol == "trap_spike":
        terrain = "trap_spike"
        draw_trap(frame, *center)
    elif symbol == "trap_abyss":
        terrain = "trap_abyss"
        draw_abyss(frame, *center)
    elif symbol == "gap":
        terrain = "gap"
        draw_gap(frame, *center)
    elif symbol == "bridge":
        terrain = "bridge"
        draw_bridge(frame, *center)
    elif symbol.startswith("chest_"):
        # Task 4 reveals its final chest on top of a rotating bridge.  Keep the
        # renderer's real draw order so the object head learns to separate the
        # chest silhouette from the stronger bridge texture underneath it.
        if rng.random() < 0.55:
            terrain = "bridge"
            draw_bridge(frame, *center)
        obj = "chest"
        state_relevant = True
        changed = symbol.endswith("_open")
        chest = symbol.removesuffix("_closed").removesuffix("_open")
        loot_kind = chest.removeprefix("chest_")
        if loot_kind == "item":
            loot_kind = "sword"
        draw_chest(frame, *center, opened=changed, loot_kind=loot_kind)
    elif symbol == "npc":
        obj = "npc"
        draw_npc(frame, *center, COLOR_NPC)
    elif symbol.startswith("button_"):
        obj = "button"
        state_relevant = True
        changed = symbol.endswith("changed")
        draw_button(frame, *center, pressed=changed)
    elif symbol.startswith("switch_"):
        obj = "switch"
        state_relevant = True
        changed = symbol.endswith("changed")
        draw_switch(frame, *center, activated=changed)
    elif symbol.startswith("exit_"):
        obj = "exit"
        state_relevant = True
        changed = symbol.endswith("changed")
        exit_kind = symbol.removesuffix("_default").removesuffix("_changed")
        renderer_type = exit_kind.removeprefix("exit_")
        orientation = int(rng.integers(0, 2))
        tiles = ((1, 1), (2, 1)) if orientation == 0 else ((1, 1), (1, 2))
        if rng.random() < 0.65:
            terrain = "bridge"
            for tile in tiles:
                draw_bridge(frame, *tile)
        color = {
            "normal": COLOR_EXIT_NORMAL,
            "locked_key": COLOR_EXIT_LOCKED,
            "conditional": COLOR_EXIT_CONDITIONAL,
        }[renderer_type]
        draw_exit(frame, tiles, renderer_type, color, opened=changed)

    full_dynamic_overlay = symbol in {
        "floor",
        "trap_spike",
        "gap",
        "bridge",
    } and rng.random() < (0.7 if symbol == "bridge" else 0.25)
    if full_dynamic_overlay:
        facing = FACING_NAMES[int(rng.integers(0, len(FACING_NAMES)))]
        draw_player_sprite(frame, TILE_SIZE, TILE_SIZE, facing)
    elif rng.random() < 0.16:
        facing = FACING_NAMES[int(rng.integers(0, len(FACING_NAMES)))]
        # Partial edge occlusion teaches the static net not to erase a known tile.
        left = int(rng.choice((TILE_SIZE - 14, TILE_SIZE * 2 - 2)))
        top = int(rng.integers(TILE_SIZE - 10, TILE_SIZE + 10))
        draw_player_sprite(frame, left, top, facing)

    crop = frame[TILE_SIZE : TILE_SIZE * 2, TILE_SIZE : TILE_SIZE * 2].copy()
    return crop, StaticTargets(
        terrain=TERRAIN_NAMES.index(terrain),
        object=OBJECT_NAMES.index(obj),
        chest=CHEST_NAMES.index(chest),
        exit=EXIT_NAMES.index(exit_kind),
        state=STATE_NAMES.index("changed" if changed else "default"),
        state_relevant=state_relevant,
    )


def generate_dynamic_batch(batch_size: int, seed: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    images: list[np.ndarray] = []
    target_lists: dict[str, list[np.ndarray]] = {
        "heatmap": [],
        "offset": [],
        "offset_mask": [],
        "facing": [],
    }
    for index in range(batch_size):
        rng = np.random.default_rng(seed + index * 130363)
        image, targets = render_dynamic_sample(rng)
        variant = COLOR_VARIANTS[(seed // 11 + index) % len(COLOR_VARIANTS)]
        images.append(apply_color_variant(image, variant))
        for key in target_lists:
            target_lists[key].append(targets[key])
    return robust_frame_channels(np.stack(images)), {
        key: np.stack(values) for key, values in target_lists.items()
    }


def render_dynamic_sample(
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    frame = np.zeros((MAP_HEIGHT, MAP_WIDTH, 3), dtype=np.uint8)
    for row in range(MAP_HEIGHT // TILE_SIZE):
        for col in range(MAP_WIDTH // TILE_SIZE):
            draw_floor(frame, col, row)

    occupied_tiles: set[tuple[int, int]] = set()
    decoration_count = int(rng.integers(8, 25))
    for _ in range(decoration_count):
        col = int(rng.integers(0, MAP_WIDTH // TILE_SIZE))
        row = int(rng.integers(0, MAP_HEIGHT // TILE_SIZE))
        if (col, row) in occupied_tiles:
            continue
        occupied_tiles.add((col, row))
        decoration = int(rng.integers(0, 9))
        if decoration == 0:
            draw_wall(frame, col, row)
        elif decoration == 1:
            draw_chest(frame, col, row, opened=bool(rng.integers(0, 2)), loot_kind="key")
        elif decoration == 2:
            draw_trap(frame, col, row)
        elif decoration == 3:
            draw_abyss(frame, col, row)
        elif decoration == 4:
            draw_gap(frame, col, row)
        elif decoration == 5:
            draw_bridge(frame, col, row)
        elif decoration == 6:
            draw_button(frame, col, row, pressed=bool(rng.integers(0, 2)))
        elif decoration == 7:
            draw_switch(frame, col, row, activated=bool(rng.integers(0, 2)))
        else:
            draw_npc(frame, col, row, COLOR_NPC)

    # Exit sprites are visually close to monster eyes and outlines under
    # grayscale/high-contrast transforms, so include them as hard negatives.
    _draw_random_exits(frame, rng, int(rng.integers(1, 4)))

    centers: list[tuple[int, int, str]] = []
    player_left, player_top = _sample_entity_position(rng, centers)
    player_center = (player_left + TILE_SIZE // 2, player_top + TILE_SIZE // 2)
    centers.append((player_center[0], player_center[1], "player"))
    if rng.random() < 0.55:
        player_col = min(player_center[0] // TILE_SIZE, MAP_WIDTH // TILE_SIZE - 1)
        player_row = min(player_center[1] // TILE_SIZE, MAP_HEIGHT // TILE_SIZE - 1)
        if rng.random() < 0.65:
            rows = {player_row, max(0, player_row - 1)}
            for row in rows:
                for col in range(MAP_WIDTH // TILE_SIZE):
                    draw_bridge(frame, col, row)
        if rng.random() < 0.65:
            cols = {player_col, max(0, player_col - 1)}
            for col in cols:
                for row in range(MAP_HEIGHT // TILE_SIZE):
                    draw_bridge(frame, col, row)
        # The real renderer draws exits after dynamic bridge tiles.
        _draw_random_exits(frame, rng, int(rng.integers(1, 4)))
    facing_index = int(rng.integers(0, len(FACING_NAMES)))
    facing = FACING_NAMES[facing_index]

    monster_count = int(rng.integers(0, 5))
    for _ in range(monster_count):
        label = tuple(MONSTER_RENDER_INFO)[int(rng.integers(0, len(MONSTER_RENDER_INFO)))]
        left, top = _sample_entity_position(rng, centers)
        center = (left + TILE_SIZE // 2, top + TILE_SIZE // 2)
        centers.append((center[0], center[1], label))
        renderer_type, color = MONSTER_RENDER_INFO[label]
        draw_monster(frame, (left, top), TILE_SIZE, renderer_type, color)

    draw_player_sprite(frame, player_left, player_top, facing)
    action_roll = rng.random()
    if action_roll < 0.12:
        draw_player_shield(frame, player_left, player_top, facing)
    elif action_roll < 0.24:
        draw_player_sword(frame, player_left, player_top, facing)

    heatmap = np.zeros((len(DYNAMIC_CLASS_TO_INDEX), HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)
    offset = np.zeros((2, HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)
    offset_mask = np.zeros((1, HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)
    facing_target = np.full((HEATMAP_HEIGHT, HEATMAP_WIDTH), -1, dtype=np.int64)
    for center_x, center_y, label in centers:
        scaled_x = center_x / OUTPUT_STRIDE
        scaled_y = center_y / OUTPUT_STRIDE
        grid_x = min(max(int(scaled_x), 0), HEATMAP_WIDTH - 1)
        grid_y = min(max(int(scaled_y), 0), HEATMAP_HEIGHT - 1)
        _draw_gaussian(heatmap[DYNAMIC_CLASS_TO_INDEX[label]], grid_x, grid_y)
        offset[0, grid_y, grid_x] = scaled_x - grid_x
        offset[1, grid_y, grid_x] = scaled_y - grid_y
        offset_mask[0, grid_y, grid_x] = 1.0
        if label == "player":
            facing_target[grid_y, grid_x] = facing_index
    return frame, {
        "heatmap": heatmap,
        "offset": offset,
        "offset_mask": offset_mask,
        "facing": facing_target,
    }


def _sample_entity_position(
    rng: np.random.Generator,
    centers: list[tuple[int, int, str]],
) -> tuple[int, int]:
    for _ in range(100):
        # One axis is usually tile aligned in real movement; sample all phases.
        if rng.random() < 0.5:
            left = int(rng.integers(0, MAP_WIDTH - TILE_SIZE + 1))
            top = int(rng.integers(0, MAP_HEIGHT // TILE_SIZE)) * TILE_SIZE
        else:
            left = int(rng.integers(0, MAP_WIDTH // TILE_SIZE)) * TILE_SIZE
            top = int(rng.integers(0, MAP_HEIGHT - TILE_SIZE + 1))
        center = (left + TILE_SIZE // 2, top + TILE_SIZE // 2)
        if all(abs(center[0] - x) + abs(center[1] - y) >= 18 for x, y, _ in centers):
            return left, top
    return int(rng.integers(0, 10)) * TILE_SIZE, int(rng.integers(0, 8)) * TILE_SIZE


def _draw_random_exits(
    frame: np.ndarray,
    rng: np.random.Generator,
    count: int,
) -> None:
    for _ in range(count):
        side = int(rng.integers(0, 4))
        if side < 2:
            col = int(rng.integers(0, MAP_WIDTH // TILE_SIZE - 1))
            row = 0 if side == 0 else MAP_HEIGHT // TILE_SIZE - 1
            tiles = ((col, row), (col + 1, row))
        else:
            col = 0 if side == 2 else MAP_WIDTH // TILE_SIZE - 1
            row = int(rng.integers(0, MAP_HEIGHT // TILE_SIZE - 1))
            tiles = ((col, row), (col, row + 1))
        renderer_type = ("normal", "locked_key", "conditional")[int(rng.integers(0, 3))]
        color = {
            "normal": COLOR_EXIT_NORMAL,
            "locked_key": COLOR_EXIT_LOCKED,
            "conditional": COLOR_EXIT_CONDITIONAL,
        }[renderer_type]
        draw_exit(
            frame,
            tiles,
            renderer_type,
            color,
            opened=renderer_type == "locked_key" and bool(rng.integers(0, 2)),
        )


def _draw_gaussian(heatmap: np.ndarray, center_x: int, center_y: int) -> None:
    kernel = np.asarray(
        ((0.08, 0.28, 0.08), (0.28, 1.0, 0.28), (0.08, 0.28, 0.08)),
        dtype=np.float32,
    )
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            x = center_x + dx
            y = center_y + dy
            if 0 <= x < heatmap.shape[1] and 0 <= y < heatmap.shape[0]:
                heatmap[y, x] = max(heatmap[y, x], kernel[dy + 1, dx + 1])
