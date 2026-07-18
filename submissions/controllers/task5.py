from __future__ import annotations

from dataclasses import replace

from nesylink.core.constants import (
    ACTION_A,
    ACTION_B,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
    MONSTER_STUN_TICKS,
    SHIELD_RAISE_DURATION_TICKS,
    TILE_SIZE,
)

from .task4 import RoomExplorer
from ..planner import align_for_path_step, actions_for_tile_path, bfs_path
from ..state import AgentMemory, SymbolicState


class Task5Controller:
    """Explore the room graph and satisfy locally visible objectives."""

    GUARD_DISTANCE_PX = 32
    GUARD_INTERVAL = SHIELD_RAISE_DURATION_TICKS

    def __init__(self) -> None:
        self.explorer = RoomExplorer(
            include_bridges=False,
            visible_frontiers_only=True,
        )

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

    def _adjacent_monster(self, state: SymbolicState) -> bool:
        if state.player is None:
            return False
        px, py = state.player
        return any(
            abs(px - mx) + abs(py - my) == 1
            for mx, my in state.monsters
        )

    def _combat_cornered(self, state: SymbolicState) -> bool:
        if state.player is None:
            return False
        blocked = state.walls | state.chests | state.opened_chests
        blocked |= state.traps | state.gaps
        labels = state.raw_features.get("static_labels", {})
        if isinstance(labels, dict):
            blocked.update(
                pos for pos, label in labels.items() if label == "npc"
            )
        px, py = state.player
        return any(
            first in blocked and second in blocked
            for first, second in (
                ((px - 1, py - 1), (px + 1, py - 1)),
                ((px - 1, py + 1), (px + 1, py + 1)),
                ((px - 1, py - 1), (px - 1, py + 1)),
                ((px + 1, py - 1), (px + 1, py + 1)),
            )
        )

    def _monster_pixel_distance(self, state: SymbolicState) -> int | None:
        if state.player_center_px is None:
            return None
        px, py = state.player_center_px
        distances = [
            max(abs(px - obj.center_px[0]), abs(py - obj.center_px[1]))
            for obj in state.raw_features.get("dynamic_objects", ())
            if getattr(obj, "kind", "player") != "player"
            and float(getattr(obj, "confidence", 0.0)) >= 0.32
        ]
        return min(distances, default=None)

    def _about_to_cross_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
    ) -> bool:
        if state.player_center_px is None or not memory.planned_actions:
            return False
        kind = str(memory.notes.get("search_plan_kind", ""))
        if not kind.startswith("exit:"):
            return False
        direction = kind.partition(":")[2]
        expected_action = {
            "west": ACTION_LEFT,
            "east": ACTION_RIGHT,
            "north": ACTION_UP,
            "south": ACTION_DOWN,
        }.get(direction)
        if memory.planned_actions[0] != expected_action:
            return False
        x, y = state.player_center_px
        return {
            "west": x <= 10,
            "east": x >= 150,
            "north": y <= 10,
            "south": y >= 118,
        }.get(direction, False)

    def _blocked_corner_recovery(
        self,
        state: SymbolicState,
        memory: AgentMemory,
    ) -> list[int]:
        if (
            state.player is None
            or memory.last_action
            not in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}
            or not (-0.2 < memory.last_reward < -0.04)
        ):
            return []
        dx, dy = {
            ACTION_UP: (0, -1),
            ACTION_DOWN: (0, 1),
            ACTION_LEFT: (-1, 0),
            ACTION_RIGHT: (1, 0),
        }[memory.last_action]
        px, py = state.player
        recovery = align_for_path_step(
            state,
            (px + dx, py + dy),
            lookahead_tiles=2,
            center_in_corridor=True,
        )
        if recovery and len(recovery) < TILE_SIZE:
            return [recovery[0]] * TILE_SIZE
        return recovery

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        room = self.explorer.update(state, memory)
        if memory.notes.get("t5_room_marker") != room:
            memory.notes["t5_room_marker"] = room
            memory.notes["t5_room_arrival_step"] = memory.step_count
        blocked_move = (
            memory.last_action
            in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}
            and -0.2 < memory.last_reward < -0.04
        )
        closed_chests = self._closed_chests(state)
        chest_signature = tuple(sorted(closed_chests))
        recovery_signature = memory.notes.get("t5_recovery_targets")
        recovery_count = int(memory.notes.get("t5_corner_recoveries", 0))
        if (
            blocked_move
            and memory.notes.get("search_plan_kind") == "chest"
            and state.player is not None
            and closed_chests
            and min(
                abs(state.player[0] - chest[0])
                + abs(state.player[1] - chest[1])
                for chest in closed_chests
            )
            <= 2
        ):
            probe = (
                memory.current_room_key,
                state.player,
                chest_signature,
            )
            if memory.notes.get("t5_interaction_probe") != probe:
                memory.notes["t5_interaction_probe"] = probe
                return ACTION_A
        if (
            blocked_move
            and memory.notes.get("search_plan_kind") == "chest"
            and recovery_signature == chest_signature
            and recovery_count >= 2
        ):
            memory.planned_actions.clear()
            memory.notes["t5_corner_recoveries"] = 0
            return ACTION_A
        recovery = self._blocked_corner_recovery(state, memory)
        if recovery:
            if memory.notes.get("search_plan_kind") == "chest":
                if recovery_signature != chest_signature:
                    recovery_count = 0
                memory.notes["t5_recovery_targets"] = chest_signature
                memory.notes["t5_corner_recoveries"] = recovery_count + 1
            memory.planned_actions = recovery + memory.planned_actions
            return memory.planned_actions.pop(0)
        pressed_buttons = state.raw_features.get("pressed_buttons", set())
        memory.button_history.update(
            tuple(pos)
            for pos in pressed_buttons
            if isinstance(pos, (tuple, list)) and len(pos) == 2
        )
        if state.keys > 0:
            memory.notes["t5_had_key"] = True
        arrival_guard = int(memory.notes.get("search_arrival_guard", 0))
        if arrival_guard > 0:
            memory.notes["search_arrival_guard"] = arrival_guard - 1
            return ACTION_B
        known_arrival = int(memory.notes.get("t5_room_arrival_step", -1000))
        arrival_age = memory.step_count - known_arrival
        room_record = memory.notes.get("search_rooms", {}).get(room, {})
        dangerous_reentry = (
            len(room_record.get("exits", {})) >= 2
            and room_record.get("monsters_seen")
        )
        reentry_guard_windows = (
            (
                "t5_reentry_guard_early_for",
                MONSTER_STUN_TICKS - SHIELD_RAISE_DURATION_TICKS + 3,
                MONSTER_STUN_TICKS,
            ),
            (
                "t5_reentry_guard_late_for",
                MONSTER_STUN_TICKS + 3,
                MONSTER_STUN_TICKS + 3 + SHIELD_RAISE_DURATION_TICKS,
            ),
        )
        for marker, window_start, window_end in reentry_guard_windows:
            if (
                dangerous_reentry
                and window_start <= arrival_age <= window_end
                and memory.notes.get(marker) != known_arrival
            ):
                memory.notes[marker] = known_arrival
                last_guard = int(memory.notes.get("t5_last_nearby_guard", -100))
                if memory.step_count - last_guard >= SHIELD_RAISE_DURATION_TICKS:
                    return ACTION_B
        if (
            memory.notes.get("search_plan_kind") == "chest"
            and memory.planned_actions
            and memory.planned_actions[0] == ACTION_A
        ):
            return memory.planned_actions.pop(0)
        if memory.notes.get("t5_heal_done") and state.player is not None and any(
            abs(state.player[0] - chest[0])
            + abs(state.player[1] - chest[1])
            == 1
            for chest in closed_chests
        ):
            adjacent_probe = (
                memory.current_room_key,
                state.player,
                chest_signature,
            )
            if memory.notes.get("t5_adjacent_probe") != adjacent_probe:
                memory.notes["t5_adjacent_probe"] = adjacent_probe
                return ACTION_A
        if (
            memory.notes.get("search_plan_kind") == "attack"
            and memory.planned_actions
        ):
            return memory.planned_actions.pop(0)
        if state.player is not None and state.monsters:
            pixel_distance = self._monster_pixel_distance(state)
            if (
                memory.notes.get("t5_heal_done")
                and len(
                    memory.notes.get("search_rooms", {})
                    .get(room, {})
                    .get("exits", {})
                )
                >= 2
                and not self._combat_cornered(state)
                and pixel_distance is not None
                and pixel_distance <= 32
                and self._adjacent_monster(state)
            ):
                return self.explorer.attack(state, memory)
            if (
                pixel_distance is not None
                and pixel_distance <= self.GUARD_DISTANCE_PX
            ) or self._monster_blocks_route(state):
                memory.notes["t5_danger_until"] = (
                    memory.step_count + SHIELD_RAISE_DURATION_TICKS
                )
            danger_until = int(memory.notes.get("t5_danger_until", -1))
            last_guard = int(memory.notes.get("t5_last_nearby_guard", -100))
            if (
                memory.step_count <= danger_until
                and memory.step_count - last_guard >= self.GUARD_INTERVAL
            ):
                memory.notes["t5_last_nearby_guard"] = memory.step_count
                return ACTION_B
        self.explorer.clear_stale_plan(state, memory)
        if memory.planned_actions:
            if self._about_to_cross_exit(state, memory):
                last_exit_guard = int(
                    memory.notes.get("t5_last_exit_guard", -100)
                )
                if memory.step_count - last_exit_guard >= 5:
                    memory.notes["t5_last_exit_guard"] = memory.step_count
                    return ACTION_B
            return memory.planned_actions.pop(0)
        if state.player is None:
            return ACTION_NOOP

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
                avoid_monsters=False,
                shield_through_monsters=True,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return ACTION_B
            return action

        unpressed_buttons = state.buttons - memory.button_history
        if unpressed_buttons:
            if state.player in unpressed_buttons:
                memory.button_history.add(state.player)
                return ACTION_NOOP
            button_path = bfs_path(state, unpressed_buttons)
            if button_path is None and state.monsters:
                button_path = bfs_path(
                    replace(state, monsters=set()),
                    unpressed_buttons,
                )
                if button_path is not None and len(button_path) >= 2:
                    memory.planned_actions = [ACTION_B] + actions_for_tile_path(
                        button_path[:2]
                    )
                    memory.notes["search_plan_kind"] = "button"
                    memory.notes["search_plan_targets"] = tuple(
                        sorted(unpressed_buttons)
                    )
                    memory.notes["search_plan_room"] = memory.current_room_key
                    return memory.planned_actions.pop(0)
            return self.explorer.follow(
                state,
                memory,
                button_path,
                "button",
                unpressed_buttons,
            )

        direction = self.explorer.direction_to_frontier(
            state,
            memory,
            avoid_monsters=False,
            resource_priority=True,
        )
        if direction is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                direction,
                avoid_monsters=False,
                shield_before_danger=True,
                shield_through_monsters=True,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return ACTION_B
            return action

        # A key or button may have made an earlier locked/conditional edge
        # usable. Reconsider those edges before declaring exploration complete.
        retry = self.explorer.retry_direction(state, memory, room)
        if retry is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                retry,
                avoid_monsters=False,
                shield_before_danger=True,
                shield_through_monsters=True,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return ACTION_B
            return action

        direction = self.explorer.direction_to_retry(state, memory)
        if direction is not None:
            action = self.explorer.move_to_exit(
                state,
                memory,
                direction,
                avoid_monsters=False,
                shield_before_danger=True,
                shield_through_monsters=True,
            )
            if (
                action == ACTION_NOOP
                and self._monster_blocks_route(state)
            ):
                return ACTION_B
            return action

        if self._monster_blocks_route(state):
            return ACTION_B
        return ACTION_NOOP
