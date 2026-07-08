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

from planner import (
    actions_for_tile_path,
    bfs_path,
    bfs_path_to_adjacent_target,
)
from state import AgentMemory, Position, SymbolicState


TASK_PHASE_KEY = "task2_phase"


class Task2Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _follow_or_plan(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
    ) -> int | None:
        if path is None:
            return None
        actions = actions_for_tile_path(path)
        if not actions:
            return None
        memory.planned_actions = actions
        return memory.planned_actions.pop(0)

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        if memory.planned_actions:
            return memory.planned_actions.pop(0)

        if state.player is None:
            memory.notes[TASK_PHASE_KEY] = "waiting_for_vision"
            return ACTION_NOOP

        if state.monsters:
            memory.notes[TASK_PHASE_KEY] = "kill_monster"
            path = bfs_path_to_adjacent_target(state, state.monsters)
            action = self._follow_or_plan(memory, path)
            if action is not None:
                return action
            return ACTION_A

        if state.keys <= 0 and state.chests:
            memory.notes[TASK_PHASE_KEY] = "collect_key"
            path = bfs_path_to_adjacent_target(state, state.chests)
            action = self._follow_or_plan(memory, path)
            if action is not None:
                return action
            return ACTION_A

        if state.keys > 0 and state.exits:
            memory.notes[TASK_PHASE_KEY] = "exit"
            path = bfs_path(state, state.exits)
            action = self._follow_or_plan(memory, path)
            if action is not None:
                return action
            if state.player in state.exits:
                x, y = state.player
                if x == 0:
                    return ACTION_LEFT
                if x == MAP_WIDTH_TILES - 1:
                    return ACTION_RIGHT
                if y == 0:
                    return ACTION_UP
                if y == MAP_HEIGHT_TILES - 1:
                    return ACTION_DOWN

        memory.notes[TASK_PHASE_KEY] = "no_action"
        return ACTION_NOOP

