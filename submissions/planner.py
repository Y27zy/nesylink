from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Iterable, TypeVar

from nesylink.core.constants import (
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_RIGHT,
    ACTION_UP,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    TILE_SIZE,
)

from .state import Position, SymbolicState


MOVE_ACTIONS = (ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT)
Node = TypeVar("Node")


def in_bounds(pos: Position) -> bool:
    x, y = pos
    return 0 <= x < MAP_WIDTH_TILES and 0 <= y < MAP_HEIGHT_TILES


def neighbors(pos: Position) -> Iterable[Position]:
    x, y = pos
    yield (x, y - 1)
    yield (x, y + 1)
    yield (x - 1, y)
    yield (x + 1, y)


def is_safe_tile(state: SymbolicState, pos: Position) -> bool:
    if not in_bounds(pos):
        return False
    bridge_tiles = state.bridges
    blocked = state.walls | state.monsters | state.chests | state.opened_chests
    blocked |= state.traps - bridge_tiles
    blocked |= state.gaps - bridge_tiles
    static_labels = state.raw_features.get("static_labels", {})
    uncertain = state.raw_features.get("static_uncertain", set())
    if isinstance(uncertain, set) and pos in uncertain and pos != state.player:
        return False
    if isinstance(static_labels, dict) and static_labels.get(pos) == "npc":
        return False
    return pos not in blocked


def action_from_step(current: Position, nxt: Position) -> int:
    cx, cy = current
    nx, ny = nxt
    if nx == cx and ny == cy - 1:
        return ACTION_UP
    if nx == cx and ny == cy + 1:
        return ACTION_DOWN
    if nx == cx - 1 and ny == cy:
        return ACTION_LEFT
    if nx == cx + 1 and ny == cy:
        return ACTION_RIGHT
    raise ValueError(f"non-adjacent path step: {current!r} -> {nxt!r}")


def bfs_path(state: SymbolicState, goals: set[Position]) -> list[Position] | None:
    if state.player is None:
        return None
    queue: deque[Position] = deque([state.player])
    parent: dict[Position, Position | None] = {state.player: None}

    while queue:
        current = queue.popleft()
        if current in goals:
            path: list[Position] = []
            cursor: Position | None = current
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            return list(reversed(path))

        for nxt in neighbors(current):
            if nxt in parent:
                continue
            if nxt not in goals and not is_safe_tile(state, nxt):
                continue
            parent[nxt] = current
            queue.append(nxt)

    return None


def adjacent_goal_tiles(state: SymbolicState, targets: set[Position]) -> set[Position]:
    goals: set[Position] = set()
    for target in targets:
        for pos in neighbors(target):
            if is_safe_tile(state, pos):
                goals.add(pos)
    return goals


def bfs_path_to_adjacent_target(
    state: SymbolicState,
    targets: set[Position],
) -> list[Position] | None:
    return bfs_path(state, adjacent_goal_tiles(state, targets))


def actions_for_tile_path(
    path: list[Position],
    *,
    max_edges: int | None = None,
) -> list[int]:
    actions: list[int] = []
    edges = list(zip(path, path[1:]))
    if max_edges is not None:
        edges = edges[:max_edges]
    for current, nxt in edges:
        action = action_from_step(current, nxt)
        actions.extend([action] * TILE_SIZE)
    return actions


def bfs_graph_path(
    graph: dict[Node, dict[str, Node]],
    start: Node,
    is_goal: Callable[[Node], bool],
) -> list[Node] | None:
    """Return the shortest node path to a goal in a discovered room graph."""

    queue: deque[Node] = deque([start])
    parent: dict[Node, Node | None] = {start: None}
    while queue:
        node = queue.popleft()
        if is_goal(node):
            path: list[Node] = []
            cursor: Node | None = node
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            return list(reversed(path))
        for neighbor in graph.get(node, {}).values():
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    return None

def align_to_tile_center(state: SymbolicState) -> list[int]:
    """Return pixel actions that center the player in its detected tile."""
    if state.player is None:
        return []
    tx, ty = state.player
    ideal_cx = tx * TILE_SIZE + TILE_SIZE // 2
    ideal_cy = ty * TILE_SIZE + TILE_SIZE // 2
    if state.player_center_px is None:
        return []
    actual_cx, actual_cy = state.player_center_px

    dx = int(ideal_cx - actual_cx)
    dy = int(ideal_cy - actual_cy)

    actions: list[int] = []
    if dx > 0:
        actions.extend([ACTION_RIGHT] * dx)
    elif dx < 0:
        actions.extend([ACTION_LEFT] * (-dx))
    if dy > 0:
        actions.extend([ACTION_DOWN] * dy)
    elif dy < 0:
        actions.extend([ACTION_UP] * (-dy))
    return actions


def align_for_path_step(
    state: SymbolicState,
    next_tile: Position,
    *,
    clearance_px: int = 3,
    lookahead_tiles: int = 1,
    center_in_corridor: bool = False,
    tolerance_px: int = 0,
) -> list[int]:
    """Move away from a corner obstacle before traversing the next tile edge."""

    if state.player is None or state.player_center_px is None:
        return []
    px, py = state.player
    nx, ny = next_tile
    blocked = state.walls | state.chests | state.opened_chests
    blocked |= (state.traps | state.gaps) - state.bridges
    labels = state.raw_features.get("static_labels", {})
    if isinstance(labels, dict):
        blocked.update(pos for pos, label in labels.items() if label == "npc")

    center_x = px * TILE_SIZE + TILE_SIZE // 2
    center_y = py * TILE_SIZE + TILE_SIZE // 2
    desired_x = center_x
    desired_y = center_y
    needs_clearance = False
    if nx != px:
        step_x = 1 if nx > px else -1
        obstacle_above = any(
            (px + step_x * step, py - 1) in blocked
            for step in range(1, lookahead_tiles + 1)
        )
        obstacle_below = any(
            (px + step_x * step, py + 1) in blocked
            for step in range(1, lookahead_tiles + 1)
        )
        if obstacle_above and not obstacle_below:
            desired_y += clearance_px
            needs_clearance = True
        elif obstacle_below and not obstacle_above:
            desired_y -= clearance_px
            needs_clearance = True
        elif obstacle_above and obstacle_below and center_in_corridor:
            needs_clearance = True
    elif ny != py:
        step_y = 1 if ny > py else -1
        obstacle_left = any(
            (px - 1, py + step_y * step) in blocked
            for step in range(1, lookahead_tiles + 1)
        )
        obstacle_right = any(
            (px + 1, py + step_y * step) in blocked
            for step in range(1, lookahead_tiles + 1)
        )
        if obstacle_left and not obstacle_right:
            desired_x += clearance_px
            needs_clearance = True
        elif obstacle_right and not obstacle_left:
            desired_x -= clearance_px
            needs_clearance = True
        elif obstacle_left and obstacle_right and center_in_corridor:
            needs_clearance = True

    if not needs_clearance:
        return []
    min_center = TILE_SIZE // 2
    max_center_x = MAP_WIDTH_TILES * TILE_SIZE - TILE_SIZE // 2
    max_center_y = MAP_HEIGHT_TILES * TILE_SIZE - TILE_SIZE // 2
    if not (
        min_center <= desired_x <= max_center_x
        and min_center <= desired_y <= max_center_y
    ):
        return []

    actual_x, actual_y = state.player_center_px
    actions: list[int] = []
    if nx != px:
        delta = int(desired_y - actual_y)
        if delta > tolerance_px:
            actions.extend([ACTION_DOWN] * (delta - tolerance_px))
        elif delta < -tolerance_px:
            actions.extend([ACTION_UP] * (-delta - tolerance_px))
    elif ny != py:
        delta = int(desired_x - actual_x)
        if delta > tolerance_px:
            actions.extend([ACTION_RIGHT] * (delta - tolerance_px))
        elif delta < -tolerance_px:
            actions.extend([ACTION_LEFT] * (-delta - tolerance_px))
    return actions
