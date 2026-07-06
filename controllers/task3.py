from __future__ import annotations

from nesylink.core.constants import (
    ACTION_A,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
    MAP_WIDTH_TILES,
)

from planner import actions_for_tile_path, bfs_path, bfs_path_to_adjacent_target
from state import AgentMemory, Position, SymbolicState


TASK_PHASE_KEY = "task3_phase"
PLAN_KIND_KEY = "task3_plan_kind"
PLAN_TARGETS_KEY = "task3_plan_targets"
WEST_EXIT_TILES = {(0, 3), (0, 4)}
EAST_EXIT_TILES = {(MAP_WIDTH_TILES - 1, 3), (MAP_WIDTH_TILES - 1, 4)}


class Task3Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _follow_or_plan(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
        *,
        plan_kind: str | None = None,
        targets: set[Position] | None = None,
    ) -> int | None:
        if path is None:
            return None
        actions = actions_for_tile_path(path)
        if not actions:
            return None
        memory.planned_actions = actions
        if plan_kind is not None:
            memory.notes[PLAN_KIND_KEY] = plan_kind
            memory.notes[PLAN_TARGETS_KEY] = self._target_signature(targets or set())
        return memory.planned_actions.pop(0)

    def _target_signature(self, targets: set[Position]) -> tuple[Position, ...]:
        return tuple(sorted(targets))

    def _clear_stale_plan(self, state: SymbolicState, memory: AgentMemory) -> None:
        plan_kind = memory.notes.get(PLAN_KIND_KEY)
        planned_targets = memory.notes.get(PLAN_TARGETS_KEY)
        current_targets: tuple[Position, ...] | None = None

        if plan_kind == "monster":
            current_targets = self._target_signature(state.monsters)
        elif plan_kind == "chest":
            current_targets = self._target_signature(state.chests)
        elif plan_kind == "west_exit" and state.keys > 0:
            current_targets = ()

        if current_targets is not None and current_targets != planned_targets:
            memory.planned_actions.clear()
            memory.notes.pop(PLAN_KIND_KEY, None)
            memory.notes.pop(PLAN_TARGETS_KEY, None)

    def _directional_exit_goals(self, state: SymbolicState, direction: str) -> set[Position]:
        if direction == "west":
            visible = {pos for pos in state.exits if pos[0] == 0}
            return visible or WEST_EXIT_TILES
        if direction == "east":
            visible = {pos for pos in state.exits if pos[0] == MAP_WIDTH_TILES - 1}
            return visible or EAST_EXIT_TILES
        raise ValueError(f"unsupported task3 exit direction: {direction!r}")

    def _has_directional_exit(self, state: SymbolicState, direction: str) -> bool:
        if direction == "west":
            return any(pos[0] == 0 for pos in state.exits)
        if direction == "east":
            return any(pos[0] == MAP_WIDTH_TILES - 1 for pos in state.exits)
        return False

    def _move_to_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        direction: str,
    ) -> int:
        goals = self._directional_exit_goals(state, direction)
        path = bfs_path(state, goals)
        action = self._follow_or_plan(memory, path, plan_kind=f"{direction}_exit", targets=goals)
        if action is not None:
            return action
        if state.player in goals:
            return ACTION_LEFT if direction == "west" else ACTION_RIGHT
        return ACTION_LEFT if direction == "west" else ACTION_RIGHT

    def _adjacent_target(self, state: SymbolicState, targets: set[Position]) -> Position | None:
        if state.player is None:
            return None
        px, py = state.player
        for target in sorted(targets):
            tx, ty = target
            if abs(px - tx) + abs(py - ty) == 1:
                return target
        return None

    def _face_target_action(self, player: Position, target: Position) -> int | None:
        px, py = player
        tx, ty = target
        if tx == px - 1 and ty == py:
            return ACTION_LEFT
        if tx == px + 1 and ty == py:
            return ACTION_RIGHT
        if ty == py - 1 and tx == px:
            return ACTION_UP
        if ty == py + 1 and tx == px:
            return ACTION_DOWN
        return None

    def _attack_or_approach_monster(self, state: SymbolicState, memory: AgentMemory) -> int:
        adjacent = self._adjacent_target(state, state.monsters)
        if adjacent is not None and state.player is not None:
            face_action = self._face_target_action(state.player, adjacent)
            if face_action is not None:
                memory.planned_actions = [ACTION_A]
                memory.notes[PLAN_KIND_KEY] = "attack"
                memory.notes[PLAN_TARGETS_KEY] = self._target_signature(state.monsters)
                return face_action
            return ACTION_A

        path = bfs_path_to_adjacent_target(state, state.monsters)
        action = self._follow_or_plan(memory, path, plan_kind="monster", targets=state.monsters)
        if action is not None:
            return action
        return ACTION_A

    def _open_or_approach_chest(self, state: SymbolicState, memory: AgentMemory) -> int:
        if self._adjacent_target(state, state.chests) is not None:
            return ACTION_A

        path = bfs_path_to_adjacent_target(state, state.chests)
        action = self._follow_or_plan(memory, path, plan_kind="chest", targets=state.chests)
        if action is not None:
            return action
        return ACTION_A

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        self._clear_stale_plan(state, memory)
        if memory.planned_actions:
            return memory.planned_actions.pop(0)

        if state.player is None:
            memory.notes[TASK_PHASE_KEY] = "waiting_for_vision"
            return ACTION_NOOP

        if state.keys > 0:
            memory.notes[TASK_PHASE_KEY] = "return_east_to_start_or_exit"
            return self._move_to_exit(state, memory, "east")

        if state.monsters:
            memory.notes[TASK_PHASE_KEY] = "handle_monster"
            return self._attack_or_approach_monster(state, memory)

        if state.chests:
            memory.notes[TASK_PHASE_KEY] = "open_key_chest"
            return self._open_or_approach_chest(state, memory)

        if (
            state.exits
            and not self._has_directional_exit(state, "west")
            and self._has_directional_exit(state, "east")
        ):
            memory.notes[TASK_PHASE_KEY] = "waiting_for_key_update"
            return ACTION_NOOP

        memory.notes[TASK_PHASE_KEY] = "go_west_to_key_room"
        return self._move_to_exit(state, memory, "west")
