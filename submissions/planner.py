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


def actions_for_tile_path(path: list[Position]) -> list[int]:
    actions: list[int] = []
    for current, nxt in zip(path, path[1:]):
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
