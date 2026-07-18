from __future__ import annotations

from nesylink.core.constants import (
    ACTION_A,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
)

from ..state import AgentMemory, Position, SymbolicState


def adjacent_target(player: Position | None, targets: set[Position]) -> Position | None:
    if player is None:
        return None
    px, py = player
    return next(
        (
            target
            for target in sorted(targets)
            if abs(px - target[0]) + abs(py - target[1]) == 1
        ),
        None,
    )


def face_target(player: Position, target: Position) -> int:
    px, py = player
    tx, ty = target
    if tx < px:
        return ACTION_LEFT
    if tx > px:
        return ACTION_RIGHT
    if ty < py:
        return ACTION_UP
    if ty > py:
        return ACTION_DOWN
    return ACTION_A


def face_then_interact(
    state: SymbolicState,
    memory: AgentMemory,
    targets: set[Position],
) -> int | None:
    """Face an adjacent target, then confirm the interaction next frame."""

    target = adjacent_target(state.player, targets)
    if target is None or state.player is None:
        return None
    desired_action = face_target(state.player, target)
    desired_facing = {
        ACTION_UP: "up",
        ACTION_DOWN: "down",
        ACTION_LEFT: "left",
        ACTION_RIGHT: "right",
    }.get(desired_action)
    if desired_facing is not None and state.player_facing == desired_facing:
        return ACTION_A
    memory.planned_actions = [ACTION_A]
    return desired_action


def boundary_cross_action(pos: Position) -> int | None:
    x, y = pos
    if x == 0:
        return ACTION_LEFT
    if x == MAP_WIDTH_TILES - 1:
        return ACTION_RIGHT
    if y == 0:
        return ACTION_UP
    if y == MAP_HEIGHT_TILES - 1:
        return ACTION_DOWN
    return None


class BaseController:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        del state, memory
        return ACTION_NOOP
