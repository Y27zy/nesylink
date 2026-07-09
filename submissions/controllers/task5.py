from __future__ import annotations

from nesylink.core.constants import ACTION_B, ACTION_NOOP

from .task4 import RoomExplorer
from ..planner import bfs_path
from ..state import AgentMemory, SymbolicState


class Task5Controller:
    """Explore the room graph and satisfy locally visible objectives."""

    def __init__(self) -> None:
        self.explorer = RoomExplorer()

    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _closed_chests(self, state: SymbolicState) -> set[tuple[int, int]]:
        return state.chests - state.opened_chests

    def _monster_blocks_route(self, state: SymbolicState) -> bool:
        if state.player is None or not state.monsters:
            return False
        px, py = state.player
        return min(
            abs(px - mx) + abs(py - my) for mx, my in state.monsters
        ) <= 2

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        room = self.explorer.update(state, memory)
        if state.keys > 0:
            memory.notes["t5_had_key"] = True
        arrival_guard = int(memory.notes.get("search_arrival_guard", 0))
        if arrival_guard > 0:
            memory.notes["search_arrival_guard"] = arrival_guard - 1
            return ACTION_B
        if (
            memory.notes.get("search_new_room_danger")
            and state.player is not None
            and state.monsters
        ):
            px, py = state.player
            distance = min(
                abs(px - mx) + abs(py - my) for mx, my in state.monsters
            )
            last_guard = int(memory.notes.get("search_new_room_last_guard", -100))
            if distance <= 2 and memory.step_count - last_guard >= 8:
                memory.notes["search_new_room_last_guard"] = memory.step_count
                return ACTION_B
        self.explorer.clear_stale_plan(state, memory)
        if memory.planned_actions:
            return memory.planned_actions.pop(0)
        if state.player is None:
            return ACTION_NOOP

        unpressed_buttons = state.buttons - memory.button_history
        if unpressed_buttons:
            if state.player in unpressed_buttons:
                memory.button_history.add(state.player)
                return ACTION_NOOP
            return self.explorer.follow(
                memory,
                bfs_path(state, unpressed_buttons),
                "button",
                unpressed_buttons,
            )

        closed_chests = self._closed_chests(state)
        if any(
            pos in state.opened_chests and label == "chest_heal"
            for pos, label in state.chest_types.items()
        ):
            memory.notes["t5_heal_done"] = True
        key_chests = {
            pos
            for pos in closed_chests
            if state.chest_types.get(pos) == "chest_key"
        }
        conditional_ready = bool(memory.button_history) and any(
            label == "exit_conditional" for label in state.exit_types.values()
        )
        locked_ready = state.keys > 0 and any(
            label == "exit_locked_key" for label in state.exit_types.values()
        )
        targets = key_chests or closed_chests
        defer_optional_chest = (
            not memory.notes.get("t5_had_key")
            and conditional_ready
            and not key_chests
        ) or (
            locked_ready
            and not memory.notes.get("t5_heal_done")
            and not key_chests
        )
        if targets and not defer_optional_chest:
            action = self.explorer.interact(
                state,
                memory,
                targets,
                "chest",
                avoid_monsters=memory.step_count < 900,
                shield_through_monsters=memory.step_count >= 900,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return self.explorer.attack(state, memory)
            return action

        direction = self.explorer.direction_to_frontier(
            state,
            memory,
            avoid_monsters=memory.step_count < 900,
            resource_priority=True,
        )
        if direction is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                direction,
                avoid_monsters=memory.step_count < 900,
                shield_before_danger=True,
                shield_through_monsters=memory.step_count >= 900,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return self.explorer.attack(state, memory)
            return action

        # A key or button may have made an earlier locked/conditional edge
        # usable. Reconsider those edges before declaring exploration complete.
        retry = self.explorer.retry_direction(state, memory, room)
        if retry is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                retry,
                avoid_monsters=memory.step_count < 900,
                shield_before_danger=True,
                shield_through_monsters=memory.step_count >= 900,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return self.explorer.attack(state, memory)
            return action

        direction = self.explorer.direction_to_retry(state, memory)
        if direction is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                direction,
                avoid_monsters=memory.step_count < 900,
                shield_before_danger=True,
                shield_through_monsters=memory.step_count >= 900,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return self.explorer.attack(state, memory)
            return action

        if self._monster_blocks_route(state):
            return self.explorer.attack(state, memory)
        return ACTION_NOOP
