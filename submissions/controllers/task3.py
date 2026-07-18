from __future__ import annotations

from collections import deque
from collections.abc import Callable

from nesylink.core.constants import (
    ACTION_A,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
    TILE_SIZE,
)

from ..planner import actions_for_tile_path, bfs_path, bfs_path_to_adjacent_target
from ..state import AgentMemory, Position, SymbolicState
from .base import face_then_interact


TASK_PHASE_KEY = "task3_phase"
PLAN_KIND_KEY = "task3_plan_kind"
PLAN_TARGETS_KEY = "task3_plan_targets"
PLAN_ROOM_KEY = "task3_plan_room"
PLAN_KEYS_KEY = "task3_plan_keys"

ROOM_COUNTER_KEY = "task3_room_counter"
ROOM_FINGERPRINTS_KEY = "task3_room_fingerprints"
ROOM_EXITS_KEY = "task3_room_exits"
ROOM_EXIT_TILES_KEY = "task3_room_exit_tiles"
ROOM_GRAPH_KEY = "task3_room_graph"
TRIED_EXITS_KEY = "task3_tried_exits"
BLOCKED_EXITS_KEY = "task3_blocked_exits"
KEY_GATED_EXITS_KEY = "task3_key_gated_exits"
PENDING_EXIT_KEY = "task3_pending_exit"

DIRECTIONS = ("north", "east", "south", "west")
OPPOSITE = {
    "north": "south",
    "south": "north",
    "west": "east",
    "east": "west",
}
CROSS_ACTION = {
    "north": ACTION_UP,
    "south": ACTION_DOWN,
    "west": ACTION_LEFT,
    "east": ACTION_RIGHT,
}
ACTION_DIRECTION = {
    ACTION_UP: "north",
    ACTION_RIGHT: "east",
    ACTION_DOWN: "south",
    ACTION_LEFT: "west",
}


class Task3Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _note_dict(self, memory: AgentMemory, key: str) -> dict:
        value = memory.notes.get(key)
        if not isinstance(value, dict):
            value = {}
            memory.notes[key] = value
        return value

    def _note_set(self, memory: AgentMemory, key: str) -> set:
        value = memory.notes.get(key)
        if not isinstance(value, set):
            value = set(value or ())
            memory.notes[key] = value
        return value

    def _target_signature(self, targets: set[Position]) -> tuple[Position, ...]:
        return tuple(sorted(targets))

    def _clear_plan_metadata(self, memory: AgentMemory) -> None:
        for key in (PLAN_KIND_KEY, PLAN_TARGETS_KEY, PLAN_ROOM_KEY, PLAN_KEYS_KEY):
            memory.notes.pop(key, None)

    def _visible_exits_by_direction(self, state: SymbolicState) -> dict[str, set[Position]]:
        exits: dict[str, set[Position]] = {direction: set() for direction in DIRECTIONS}
        for x, y in state.exits:
            if x == 0:
                exits["west"].add((x, y))
            if x == MAP_WIDTH_TILES - 1:
                exits["east"].add((x, y))
            if y == 0:
                exits["north"].add((x, y))
            if y == MAP_HEIGHT_TILES - 1:
                exits["south"].add((x, y))
        return {direction: tiles for direction, tiles in exits.items() if tiles}

    def _exit_goals(
        self,
        state: SymbolicState,
        direction: str,
        memory: AgentMemory | None = None,
    ) -> set[Position]:
        visible = self._visible_exits_by_direction(state).get(direction, set())
        if visible or memory is None or memory.current_room_key is None:
            return visible
        room_exit_tiles = self._note_dict(memory, ROOM_EXIT_TILES_KEY)
        remembered = room_exit_tiles.get(memory.current_room_key, {}).get(direction, set())
        return set(remembered)

    def _room_fingerprint(self, state: SymbolicState) -> tuple:
        exits = self._visible_exits_by_direction(state)
        return (
            ("walls", tuple(sorted(state.walls))),
            ("floors", tuple(sorted(state.floors))),
            (
                "exits",
                tuple(
                    (direction, tuple(sorted(exits[direction])))
                    for direction in DIRECTIONS
                    if direction in exits
                ),
            ),
            ("traps", tuple(sorted(state.traps))),
            ("gaps", tuple(sorted(state.gaps))),
            ("bridges", tuple(sorted(state.bridges))),
        )

    def _new_room_key(self, memory: AgentMemory) -> str:
        index = int(memory.notes.get(ROOM_COUNTER_KEY, 0))
        memory.notes[ROOM_COUNTER_KEY] = index + 1
        return f"task3_room_{index}"

    def _record_room_observation(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room_key: str,
    ) -> None:
        visible_exits = self._visible_exits_by_direction(state)
        fingerprints = self._note_dict(memory, ROOM_FINGERPRINTS_KEY)
        exits_by_room = self._note_dict(memory, ROOM_EXITS_KEY)
        exit_tiles_by_room = self._note_dict(memory, ROOM_EXIT_TILES_KEY)
        if visible_exits or room_key not in fingerprints:
            fingerprints[room_key] = self._room_fingerprint(state)
        exits_by_room[room_key] = set(exits_by_room.get(room_key, set())) | set(visible_exits)
        room_exit_tiles = exit_tiles_by_room.setdefault(room_key, {})
        for direction, tiles in visible_exits.items():
            room_exit_tiles[direction] = set(room_exit_tiles.get(direction, set())) | set(tiles)
        memory.current_room_key = room_key
        memory.visited_rooms.add(room_key)

    def _remember_corridor_continuation(
        self,
        memory: AgentMemory,
        room_key: str,
    ) -> None:
        exits_by_room = self._note_dict(memory, ROOM_EXITS_KEY)
        known_directions = set(exits_by_room.get(room_key, set()))
        if len(known_directions) != 1:
            return
        entry_direction = next(iter(known_directions))
        direction = OPPOSITE[entry_direction]
        edge = (room_key, direction)
        if edge in self._note_set(memory, BLOCKED_EXITS_KEY):
            return
        exit_tiles_by_room = self._note_dict(memory, ROOM_EXIT_TILES_KEY)
        room_tiles = exit_tiles_by_room.setdefault(room_key, {})
        source_tiles = set(room_tiles.get(entry_direction, set()))
        if not source_tiles:
            return
        if direction == "west":
            candidate_tiles = {(0, y) for _, y in source_tiles}
        elif direction == "east":
            candidate_tiles = {(MAP_WIDTH_TILES - 1, y) for _, y in source_tiles}
        elif direction == "north":
            candidate_tiles = {(x, 0) for x, _ in source_tiles}
        else:
            candidate_tiles = {(x, MAP_HEIGHT_TILES - 1) for x, _ in source_tiles}
        exits_by_room[room_key] = known_directions | {direction}
        room_tiles[direction] = candidate_tiles

    def _ensure_current_room(self, state: SymbolicState, memory: AgentMemory) -> str:
        if memory.current_room_key is None:
            memory.current_room_key = self._new_room_key(memory)
        self._record_room_observation(state, memory, memory.current_room_key)
        return memory.current_room_key

    def _mark_exit_blocked(
        self,
        memory: AgentMemory,
        room_key: str,
        direction: str,
        *,
        keys_before_attempt: int,
    ) -> None:
        edge = (room_key, direction)
        self._note_set(memory, BLOCKED_EXITS_KEY).add(edge)
        if keys_before_attempt <= 0:
            self._note_set(memory, KEY_GATED_EXITS_KEY).add(edge)

    def _resolve_pending_exit(self, state: SymbolicState, memory: AgentMemory) -> None:
        pending = memory.notes.get(PENDING_EXIT_KEY)
        if not isinstance(pending, dict) or state.player is None:
            return

        from_room = str(pending.get("from_room", memory.current_room_key or ""))
        direction = str(pending.get("direction", ""))
        exit_tiles = {tuple(pos) for pos in pending.get("exit_tiles", ())}
        keys_before_attempt = int(pending.get("keys", 0))
        if direction not in OPPOSITE or not from_room:
            memory.notes.pop(PENDING_EXIT_KEY, None)
            return

        if state.player in exit_tiles:
            remaining = int(pending.get("remaining_cross_actions", 0))
            if remaining > 0:
                pending["remaining_cross_actions"] = remaining - 1
                return
            self._mark_exit_blocked(
                memory,
                from_room,
                direction,
                keys_before_attempt=keys_before_attempt,
            )
            memory.current_room_key = from_room
            memory.notes.pop(PENDING_EXIT_KEY, None)
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)
            memory.notes[TASK_PHASE_KEY] = "exit_blocked"
            return

        transitioned = (
            memory.last_reward > 5.0
            and memory.last_action == CROSS_ACTION.get(direction)
        )
        if not transitioned:
            remaining = int(pending.get("remaining_cross_actions", 0))
            if remaining > 0:
                pending["remaining_cross_actions"] = remaining - 1
                return
            self._mark_exit_blocked(
                memory,
                from_room,
                direction,
                keys_before_attempt=keys_before_attempt,
            )
            memory.current_room_key = from_room
            memory.notes.pop(PENDING_EXIT_KEY, None)
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)
            memory.notes[TASK_PHASE_KEY] = "exit_blocked"
            return

        graph = self._note_dict(memory, ROOM_GRAPH_KEY)
        room_edges = graph.setdefault(from_room, {})
        to_room = room_edges.get(direction)
        if to_room is None:
            to_room = self._new_room_key(memory)
            room_edges[direction] = to_room
        graph.setdefault(to_room, {})[OPPOSITE[direction]] = from_room
        self._note_set(memory, BLOCKED_EXITS_KEY).discard((from_room, direction))
        self._note_set(memory, KEY_GATED_EXITS_KEY).discard((from_room, direction))
        memory.current_room_key = to_room
        memory.notes.pop(PENDING_EXIT_KEY, None)
        memory.planned_actions.clear()
        self._clear_plan_metadata(memory)

    def _sync_visual_room(self, state: SymbolicState, memory: AgentMemory) -> bool:
        """Detect room changes even when movement crosses before `_cross_exit`."""

        vision_key = state.raw_features.get("vision_room_key")
        if not isinstance(vision_key, str):
            return False
        visual_rooms = self._note_dict(memory, "task3_visual_rooms")
        previous_key = memory.notes.get("task3_last_visual_room")
        if memory.current_room_key is None:
            memory.current_room_key = visual_rooms.get(vision_key) or self._new_room_key(memory)
        if previous_key is None:
            memory.notes["task3_last_visual_room"] = vision_key
            visual_rooms.setdefault(vision_key, memory.current_room_key)
            return False
        if previous_key == vision_key:
            visual_rooms.setdefault(vision_key, memory.current_room_key)
            return False

        source = memory.current_room_key
        destination = visual_rooms.get(vision_key)
        direction = ACTION_DIRECTION.get(memory.last_action)
        if memory.last_reward <= 5.0 or direction is None:
            return False
        memory.notes["task3_last_visual_room"] = vision_key
        if destination is None:
            destination = self._new_room_key(memory)
            visual_rooms[vision_key] = destination
        if source is not None and direction is not None and source != destination:
            graph = self._note_dict(memory, ROOM_GRAPH_KEY)
            graph.setdefault(source, {})[direction] = destination
            graph.setdefault(destination, {})[OPPOSITE[direction]] = source
            self._note_set(memory, TRIED_EXITS_KEY).add((source, direction))
            self._note_set(memory, BLOCKED_EXITS_KEY).discard((source, direction))
            self._note_set(memory, KEY_GATED_EXITS_KEY).discard((source, direction))
        memory.current_room_key = destination
        memory.notes.pop(PENDING_EXIT_KEY, None)
        memory.planned_actions.clear()
        self._clear_plan_metadata(memory)
        return True

    def _update_room_tracking(self, state: SymbolicState, memory: AgentMemory) -> str:
        if memory.current_room_key is None:
            memory.current_room_key = self._new_room_key(memory)
        changed = self._sync_visual_room(state, memory)
        if not changed:
            self._resolve_pending_exit(state, memory)
        return self._ensure_current_room(state, memory)

    def _clear_stale_plan(self, state: SymbolicState, memory: AgentMemory) -> None:
        plan_kind = memory.notes.get(PLAN_KIND_KEY)
        if plan_kind is None:
            return

        plan_room = memory.notes.get(PLAN_ROOM_KEY)
        if plan_room is not None and plan_room != memory.current_room_key:
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)
            return

        planned_keys = memory.notes.get(PLAN_KEYS_KEY)
        if planned_keys is not None and planned_keys != state.keys:
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)
            return

        planned_targets = memory.notes.get(PLAN_TARGETS_KEY)
        current_targets: tuple[Position, ...] | None = None
        if plan_kind == "monster":
            current_targets = self._target_signature(state.monsters)
        elif plan_kind == "chest":
            current_targets = self._target_signature(state.chests - state.opened_chests)
        elif isinstance(plan_kind, str) and plan_kind.endswith("_exit"):
            direction = plan_kind.removesuffix("_exit")
            current_targets = self._target_signature(self._exit_goals(state, direction, memory))

        if current_targets is not None and current_targets != planned_targets:
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)

    def _follow_or_plan(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        path: list[Position] | None,
        *,
        plan_kind: str | None = None,
        targets: set[Position] | None = None,
    ) -> int | None:
        if path is None:
            return None
        actions = actions_for_tile_path(path, max_edges=1)
        if not actions:
            return None
        memory.planned_actions = actions
        if plan_kind is not None:
            memory.notes[PLAN_KIND_KEY] = plan_kind
            memory.notes[PLAN_TARGETS_KEY] = self._target_signature(targets or set())
            memory.notes[PLAN_ROOM_KEY] = memory.current_room_key
            memory.notes[PLAN_KEYS_KEY] = state.keys
        return memory.planned_actions.pop(0)

    def _cross_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        direction: str,
        goals: set[Position],
    ) -> int:
        room_key = self._ensure_current_room(state, memory)
        self._note_set(memory, TRIED_EXITS_KEY).add((room_key, direction))
        memory.notes[PENDING_EXIT_KEY] = {
            "from_room": room_key,
            "direction": direction,
            "exit_tiles": tuple(sorted(goals)),
            "keys": state.keys,
            # Tile coordinates do not reveal the player's sub-tile pixel
            # offset. Keep pressing across the boundary for at most one tile
            # before deciding that an exit is actually blocked.
            "remaining_cross_actions": TILE_SIZE - 1,
        }
        self._clear_plan_metadata(memory)
        return CROSS_ACTION[direction]

    def _move_to_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        direction: str,
    ) -> int | None:
        goals = self._exit_goals(state, direction, memory)
        if not goals:
            return None
        if state.player in goals:
            return self._cross_exit(state, memory, direction, goals)
        path = bfs_path(state, goals)
        return self._follow_or_plan(
            state,
            memory,
            path,
            plan_kind=f"{direction}_exit",
            targets=goals,
        )

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
                memory.notes[PLAN_ROOM_KEY] = memory.current_room_key
                memory.notes[PLAN_KEYS_KEY] = state.keys
                return face_action
            return ACTION_A

        path = bfs_path_to_adjacent_target(state, state.monsters)
        action = self._follow_or_plan(
            state,
            memory,
            path,
            plan_kind="monster",
            targets=state.monsters,
        )
        if action is not None:
            return action
        return ACTION_NOOP

    def _open_or_approach_chest(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        chests: set[Position],
    ) -> int:
        interaction = face_then_interact(state, memory, chests)
        if interaction is not None:
            return interaction

        path = bfs_path_to_adjacent_target(state, chests)
        action = self._follow_or_plan(
            state,
            memory,
            path,
            plan_kind="chest",
            targets=chests,
        )
        if action is not None:
            return action
        return ACTION_NOOP

    def _exit_blocked_for_now(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room_key: str,
        direction: str,
    ) -> bool:
        edge = (room_key, direction)
        blocked = self._note_set(memory, BLOCKED_EXITS_KEY)
        if edge not in blocked:
            return False
        key_gated = self._note_set(memory, KEY_GATED_EXITS_KEY)
        return not (state.keys > 0 and edge in key_gated)

    def _nearest_reachable_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        directions: set[str],
    ) -> str | None:
        best: tuple[int, int, str] | None = None
        for direction in DIRECTIONS:
            if direction not in directions:
                continue
            goals = self._exit_goals(state, direction, memory)
            if not goals:
                continue
            path = bfs_path(state, goals)
            if path is None and state.player not in goals:
                continue
            distance = 0 if state.player in goals else len(path or ())
            score = (distance, DIRECTIONS.index(direction), direction)
            if best is None or score < best:
                best = score
        return None if best is None else best[2]

    def _frontier_dirs_for_room(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room_key: str,
    ) -> set[str]:
        exits_by_room = self._note_dict(memory, ROOM_EXITS_KEY)
        tried = self._note_set(memory, TRIED_EXITS_KEY)
        exits = set(exits_by_room.get(room_key, set()))
        return {
            direction
            for direction in exits
            if (room_key, direction) not in tried
            and not self._exit_blocked_for_now(state, memory, room_key, direction)
        }

    def _route_to_room(
        self,
        memory: AgentMemory,
        start: str,
        predicate: Callable[[str], bool],
    ) -> list[str] | None:
        graph = self._note_dict(memory, ROOM_GRAPH_KEY)
        queue: deque[str] = deque([start])
        parent: dict[str, str | None] = {start: None}

        while queue:
            room = queue.popleft()
            if room != start and predicate(room):
                path: list[str] = []
                cursor: str | None = room
                while cursor is not None:
                    path.append(cursor)
                    cursor = parent[cursor]
                return list(reversed(path))

            for direction in DIRECTIONS:
                next_room = graph.get(room, {}).get(direction)
                if next_room is None or next_room in parent:
                    continue
                parent[next_room] = room
                queue.append(next_room)
        return None

    def _direction_to_neighbor(self, memory: AgentMemory, room: str, neighbor: str) -> str | None:
        graph = self._note_dict(memory, ROOM_GRAPH_KEY)
        for direction in DIRECTIONS:
            if graph.get(room, {}).get(direction) == neighbor:
                return direction
        return None

    def _route_direction_to_frontier(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room_key: str,
    ) -> str | None:
        route = self._route_to_room(
            memory,
            room_key,
            lambda room: bool(self._frontier_dirs_for_room(state, memory, room)),
        )
        if route is None or len(route) < 2:
            return None
        return self._direction_to_neighbor(memory, route[0], route[1])

    def _route_direction_to_key_gated_exit(
        self,
        memory: AgentMemory,
        room_key: str,
    ) -> str | None:
        key_gated = self._note_set(memory, KEY_GATED_EXITS_KEY)
        route = self._route_to_room(
            memory,
            room_key,
            lambda room: any(edge_room == room for edge_room, _ in key_gated),
        )
        if route is None or len(route) < 2:
            return None
        return self._direction_to_neighbor(memory, route[0], route[1])

    def _select_exit_direction(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room_key: str,
    ) -> str | None:
        visible_dirs = set(self._visible_exits_by_direction(state))
        known_dirs = visible_dirs | set(self._note_dict(memory, ROOM_EXITS_KEY).get(room_key, set()))
        if not known_dirs:
            memory.notes[TASK_PHASE_KEY] = "no_visible_exit"
            return None

        key_gated = self._note_set(memory, KEY_GATED_EXITS_KEY)
        if state.keys > 0:
            retry_here = {
                direction
                for direction in known_dirs
                if (room_key, direction) in key_gated
            }
            direction = self._nearest_reachable_exit(state, memory, retry_here)
            if direction is not None:
                memory.notes[TASK_PHASE_KEY] = "retry_key_gated_exit"
                return direction

        frontier_here = self._frontier_dirs_for_room(state, memory, room_key) & known_dirs
        direction = self._nearest_reachable_exit(state, memory, frontier_here)
        if direction is not None:
            memory.notes[TASK_PHASE_KEY] = (
                "explore_with_key" if state.keys > 0 else "explore_for_key"
            )
            return direction

        if state.keys > 0:
            direction = self._route_direction_to_key_gated_exit(memory, room_key)
            if direction is not None:
                memory.notes[TASK_PHASE_KEY] = "route_to_key_gated_exit"
                return direction

        direction = self._route_direction_to_frontier(state, memory, room_key)
        if direction is not None:
            memory.notes[TASK_PHASE_KEY] = "route_to_frontier"
            return direction

        fallback = {
            direction
            for direction in known_dirs
            if not self._exit_blocked_for_now(state, memory, room_key, direction)
        }
        direction = self._nearest_reachable_exit(state, memory, fallback)
        if direction is not None:
            memory.notes[TASK_PHASE_KEY] = "backtrack_or_retry_exit"
            return direction

        memory.notes[TASK_PHASE_KEY] = "no_exit_goal"
        return None

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        if state.player is None:
            memory.notes[TASK_PHASE_KEY] = "waiting_for_vision"
            return ACTION_NOOP

        room_key = self._update_room_tracking(state, memory)
        previous_phase = memory.notes.get(TASK_PHASE_KEY)
        if previous_phase == "handle_monster" and not state.monsters:
            memory.notes["expect_new_static_chest"] = True
            memory.notes["task3_reveal_scan_remaining"] = 12
            memory.planned_actions.clear()
            self._clear_plan_metadata(memory)
        reveal_scan = int(memory.notes.get("task3_reveal_scan_remaining", 0))
        if reveal_scan > 0 and not (state.chests - state.opened_chests):
            memory.notes["task3_reveal_scan_remaining"] = reveal_scan - 1
            memory.notes[TASK_PHASE_KEY] = "scan_revealed_chest"
            return ACTION_NOOP
        if state.chests - state.opened_chests:
            memory.notes.pop("task3_reveal_scan_remaining", None)
        if state.keys > 0:
            memory.notes.pop("expect_new_static_chest", None)
        pending = memory.notes.get(PENDING_EXIT_KEY)
        if isinstance(pending, dict):
            direction = pending.get("direction")
            if direction in CROSS_ACTION:
                return CROSS_ACTION[direction]
        self._clear_stale_plan(state, memory)
        if memory.planned_actions:
            return memory.planned_actions.pop(0)

        if state.monsters:
            memory.notes[TASK_PHASE_KEY] = "handle_monster"
            return self._attack_or_approach_monster(state, memory)

        active_chests = state.chests - state.opened_chests
        if state.keys <= 0 and active_chests:
            memory.notes[TASK_PHASE_KEY] = "open_key_chest"
            return self._open_or_approach_chest(state, memory, active_chests)

        if state.keys <= 0 and state.opened_chests:
            memory.notes[TASK_PHASE_KEY] = "waiting_for_key_update"
            return ACTION_NOOP

        if state.keys <= 0 and memory.notes.get("expect_new_static_chest"):
            self._remember_corridor_continuation(memory, room_key)

        direction = self._select_exit_direction(state, memory, room_key)
        if direction is None:
            return ACTION_NOOP

        action = self._move_to_exit(state, memory, direction)
        return action if action is not None else ACTION_NOOP
