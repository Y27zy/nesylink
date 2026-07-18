from __future__ import annotations

from nesylink.core.constants import ACTION_NOOP

from ..planner import (
    actions_for_tile_path,
    bfs_path,
    bfs_path_to_adjacent_target,
)
from ..state import AgentMemory, Position, SymbolicState
from .base import boundary_cross_action, face_then_interact


TASK_PHASE_KEY = "task1_phase"


class Task1Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _follow_or_plan(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
    ) -> int | None:
        if path is None:
            return None
        actions = actions_for_tile_path(path, max_edges=1)
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

        closed_chests = state.chests - state.opened_chests
        if state.keys <= 0 and closed_chests:
            memory.notes[TASK_PHASE_KEY] = "collect_key"
            path = bfs_path_to_adjacent_target(state, closed_chests)
            action = self._follow_or_plan(memory, path)
            if action is not None:
                return action
            interaction = face_then_interact(state, memory, closed_chests)
            return interaction if interaction is not None else ACTION_NOOP

        if state.keys > 0 and state.exits:
            memory.notes[TASK_PHASE_KEY] = "exit"
            path = bfs_path(state, state.exits)
            action = self._follow_or_plan(memory, path)
            if action is not None:
                return action
            if state.player in state.exits:
                crossing = boundary_cross_action(state.player)
                return crossing if crossing is not None else ACTION_NOOP

        if state.keys > 0 and state.player is not None and state.player[1] == 0:
            memory.notes[TASK_PHASE_KEY] = "exit_north"
            crossing = boundary_cross_action(state.player)
            return crossing if crossing is not None else ACTION_NOOP

        memory.notes[TASK_PHASE_KEY] = "no_action"
        return ACTION_NOOP

