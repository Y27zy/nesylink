from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from nesylink.core.constants import (
    ACTION_A,
    ACTION_B,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
)

from ..planner import (
    actions_for_tile_path,
    bfs_graph_path,
    bfs_path,
    bfs_path_to_adjacent_target,
)
from ..state import AgentMemory, Position, SymbolicState


DIRECTIONS = ("north", "east", "south", "west")
OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}
CROSS_ACTION = {
    "north": ACTION_UP,
    "south": ACTION_DOWN,
    "east": ACTION_RIGHT,
    "west": ACTION_LEFT,
}


def adjacent_target(player: Position | None, targets: set[Position]) -> Position | None:
    if player is None:
        return None
    px, py = player
    for target in sorted(targets):
        tx, ty = target
        if abs(px - tx) + abs(py - ty) == 1:
            return target
    return None


def face_target(player: Position, target: Position) -> int:
    px, py = player
    tx, ty = target
    if tx == px - 1:
        return ACTION_LEFT
    if tx == px + 1:
        return ACTION_RIGHT
    if ty == py - 1:
        return ACTION_UP
    if ty == py + 1:
        return ACTION_DOWN
    return ACTION_A


class RoomExplorer:
    """Room-graph search backed by the existing AgentMemory.notes field."""

    def _graph(self, memory: AgentMemory) -> dict[str, dict[str, str]]:
        return memory.notes.setdefault("search_graph", {})

    def _rooms(self, memory: AgentMemory) -> dict[str, dict]:
        return memory.notes.setdefault("search_rooms", {})

    def _tried(self, memory: AgentMemory) -> set[tuple[str, str]]:
        return memory.notes.setdefault("search_tried", set())

    def _blocked(self, memory: AgentMemory) -> dict[tuple[str, str], tuple]:
        return memory.notes.setdefault("search_blocked", {})

    def _new_room(self, memory: AgentMemory) -> str:
        counter = int(memory.notes.get("search_room_counter", 0))
        memory.notes["search_room_counter"] = counter + 1
        room = f"room_{counter}"
        self._graph(memory).setdefault(room, {})
        self._rooms(memory).setdefault(
            room,
            {
                "exits": {},
                "switches": set(),
                "bridge_signatures": set(),
                "monsters_seen": False,
            },
        )
        return room

    def _resource_signature(self, state: SymbolicState, memory: AgentMemory) -> tuple:
        return (
            state.keys,
            tuple(sorted(state.items)),
            tuple(sorted(state.tools)),
            len(memory.button_history),
            int(memory.notes.get("switch_activations", 0)),
        )

    def _room_signature(self, state: SymbolicState) -> tuple:
        directions = tuple(sorted(self._visible_exits(state)))
        return (
            tuple(sorted(state.walls)),
            directions,
        )

    def _visible_exits(self, state: SymbolicState) -> dict[str, set[Position]]:
        result: dict[str, set[Position]] = {}
        for x, y in state.exits | state.bridges:
            direction = None
            if y == 0:
                direction = "north"
            elif x == MAP_WIDTH_TILES - 1:
                direction = "east"
            elif y == MAP_HEIGHT_TILES - 1:
                direction = "south"
            elif x == 0:
                direction = "west"
            if direction is not None:
                result.setdefault(direction, set()).add((x, y))
        return result

    def update(self, state: SymbolicState, memory: AgentMemory) -> str:
        self._learn_blocked_tile(state, memory)
        pending = memory.notes.get("search_pending")
        if isinstance(pending, dict):
            self._resolve_pending(state, memory, pending)
        else:
            self._resolve_implicit_transition(state, memory)

        if memory.current_room_key is None:
            memory.current_room_key = self._new_room(memory)
        room = memory.current_room_key
        record = self._rooms(memory).setdefault(
            room,
            {
                "exits": {},
                "switches": set(),
                "bridge_signatures": set(),
                "monsters_seen": False,
            },
        )
        for direction, tiles in self._visible_exits(state).items():
            record["exits"].setdefault(direction, set()).update(tiles)
        record["switches"].update(state.switches)
        record["monsters_seen"] = record["monsters_seen"] or bool(state.monsters)
        if state.bridges:
            record["bridge_signatures"].add(tuple(sorted(state.bridges)))
        memory.visited_rooms.add(room)
        memory.notes["search_last_signature"] = self._room_signature(state)
        return room

    def _learn_blocked_tile(
        self,
        state: SymbolicState,
        memory: AgentMemory,
    ) -> None:
        player = state.player
        previous = memory.notes.get("search_last_player")
        action = memory.notes.get("search_last_move")
        if player is None:
            return
        if player == previous and action in {
            ACTION_UP,
            ACTION_DOWN,
            ACTION_LEFT,
            ACTION_RIGHT,
        }:
            count = int(memory.notes.get("search_stagnant_steps", 0)) + 1
        else:
            count = 0
        memory.notes["search_stagnant_steps"] = count
        memory.notes["search_last_player"] = player
        if count < 24 or memory.current_room_key is None:
            return
        dx, dy = {
            ACTION_UP: (0, -1),
            ACTION_DOWN: (0, 1),
            ACTION_LEFT: (-1, 0),
            ACTION_RIGHT: (1, 0),
        }[action]
        blocked = memory.notes.setdefault("search_learned_blocked", {})
        blocked.setdefault(memory.current_room_key, set()).add(
            (player[0] + dx, player[1] + dy)
        )
        memory.planned_actions.clear()
        memory.notes["search_stagnant_steps"] = 0

    def _planning_state(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        *,
        avoid_monsters: bool,
    ) -> SymbolicState:
        result = self._avoid_monsters(state) if avoid_monsters else state
        learned = memory.notes.get("search_learned_blocked", {}).get(
            memory.current_room_key, set()
        )
        if learned:
            result = replace(result, walls=result.walls | set(learned))
        return result

    def _link_transition(
        self,
        memory: AgentMemory,
        source: str,
        direction: str,
    ) -> None:
        graph = self._graph(memory)
        destination = graph.setdefault(source, {}).get(direction)
        discovered_now = destination is None
        if destination is None:
            destination = self._new_room(memory)
            graph[source][direction] = destination
        graph.setdefault(destination, {})[OPPOSITE[direction]] = source
        self._blocked(memory).pop((source, direction), None)
        self._tried(memory).add((source, direction))
        memory.current_room_key = destination
        if (
            self._rooms(memory).get(destination, {}).get("monsters_seen")
            and memory.step_count >= 850
        ):
            memory.notes["search_arrival_guard"] = 4
        elif discovered_now and memory.step_count >= 850:
            memory.notes["search_arrival_guard"] = 8
            memory.notes["search_new_room_danger"] = True
        memory.planned_actions.clear()

    def _resolve_implicit_transition(
        self,
        state: SymbolicState,
        memory: AgentMemory,
    ) -> None:
        source = memory.current_room_key
        kind = str(memory.notes.get("search_plan_kind", ""))
        previous = memory.notes.get("search_last_signature")
        if (
            source is None
            or not kind.startswith("exit:")
            or previous is None
            or previous == self._room_signature(state)
        ):
            return
        direction = kind.split(":", 1)[1]
        if direction in OPPOSITE:
            self._link_transition(memory, source, direction)

    def _resolve_pending(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        pending: dict,
    ) -> None:
        if state.player is None:
            return
        source = str(pending["room"])
        direction = str(pending["direction"])
        targets = {tuple(pos) for pos in pending["targets"]}
        if state.player in targets:
            remaining = int(pending.get("remaining", 0))
            if remaining > 0:
                pending["remaining"] = remaining - 1
                memory.notes["search_pending"] = pending
                return
            memory.notes.pop("search_pending", None)
            memory.planned_actions.clear()
            self._blocked(memory)[(source, direction)] = tuple(pending["resources"])
            memory.current_room_key = source
            return
        memory.notes.pop("search_pending", None)
        memory.planned_actions.clear()
        self._link_transition(memory, source, direction)

    def _can_try(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room: str,
        direction: str,
    ) -> bool:
        old = self._blocked(memory).get((room, direction))
        return old is None or old != self._resource_signature(state, memory)

    def _frontier(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room: str,
    ) -> list[str]:
        exits = self._rooms(memory).get(room, {}).get("exits", {})
        return [
            direction
            for direction in DIRECTIONS
            if direction in exits
            and direction not in self._graph(memory).get(room, {})
            and (room, direction) not in self._tried(memory)
            and self._can_try(state, memory, room, direction)
        ]

    def route(
        self,
        memory: AgentMemory,
        predicate: Callable[[str], bool],
    ) -> list[str] | None:
        start = memory.current_room_key
        if start is None:
            return None
        return bfs_graph_path(self._graph(memory), start, predicate)

    def direction_toward(
        self,
        memory: AgentMemory,
        predicate: Callable[[str], bool],
    ) -> str | None:
        path = self.route(memory, predicate)
        if path is None or len(path) < 2 or memory.current_room_key is None:
            return None
        for direction, neighbor in self._graph(memory)[memory.current_room_key].items():
            if neighbor == path[1]:
                return direction
        return None

    def direction_to_frontier(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        *,
        avoid_monsters: bool = False,
        resource_priority: bool = False,
    ) -> str | None:
        room = memory.current_room_key
        if room is None:
            return None
        local = self._frontier(state, memory, room)
        if local:
            planning_state = self._planning_state(
                state, memory, avoid_monsters=avoid_monsters
            )
            ranked: list[tuple[int, int, str]] = []
            for direction in local:
                targets = set(self._visible_exits(state).get(direction, set()))
                targets.update(
                    self._rooms(memory)[room]["exits"].get(direction, set())
                )
                path = bfs_path(planning_state, targets)
                if path is not None:
                    priority = 0
                    if resource_priority:
                        labels = {
                            state.exit_types.get(target, "exit_normal")
                            for target in targets
                        }
                        if "exit_locked_key" in labels:
                            priority = 0 if state.keys > 0 else 4
                        elif "exit_conditional" in labels:
                            priority = 0 if memory.button_history else 3
                        else:
                            priority = 2
                    ranked.append((priority, len(path), direction))
            if ranked:
                return min(ranked)[2]
        return self.direction_toward(
            memory,
            lambda candidate: bool(self._frontier(state, memory, candidate)),
        )

    def retry_direction(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        room: str,
    ) -> str | None:
        for edge_room, direction in self._blocked(memory):
            if (
                edge_room == room
                and direction not in self._graph(memory).get(room, {})
                and self._can_try(state, memory, room, direction)
            ):
                self._tried(memory).discard((room, direction))
                return direction
        return None

    def direction_to_retry(
        self,
        state: SymbolicState,
        memory: AgentMemory,
    ) -> str | None:
        return self.direction_toward(
            memory,
            lambda room: any(
                edge_room == room
                and self._can_try(state, memory, edge_room, direction)
                for edge_room, direction in self._blocked(memory)
            ),
        )

    def move_to_exit(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        direction: str,
        *,
        avoid_monsters: bool = False,
        shield_before_danger: bool = False,
        shield_through_monsters: bool = False,
    ) -> int:
        room = memory.current_room_key
        if room is None or state.player is None:
            return ACTION_NOOP
        visible = self._visible_exits(state).get(direction, set())
        remembered = self._rooms(memory)[room]["exits"].get(direction, set())
        targets = set(visible) | set(remembered)
        if not targets:
            return ACTION_NOOP
        if state.player in targets:
            self._tried(memory).add((room, direction))
            destination = self._graph(memory).get(room, {}).get(direction)
            dangerous = bool(
                destination
                and self._rooms(memory).get(destination, {}).get("monsters_seen")
            )
            shield_actions = (
                [ACTION_B] if shield_before_danger and dangerous else []
            )
            crossing_actions = shield_actions + [CROSS_ACTION[direction]] * 16
            memory.notes["search_pending"] = {
                "room": room,
                "direction": direction,
                "targets": tuple(sorted(targets)),
                "resources": self._resource_signature(state, memory),
                "remaining": len(crossing_actions) - 1,
            }
            memory.planned_actions = crossing_actions
            return memory.planned_actions.pop(0)
        planning_state = self._planning_state(
            state, memory, avoid_monsters=avoid_monsters
        )
        other_exits: set[Position] = set()
        for other_direction, tiles in self._rooms(memory)[room]["exits"].items():
            if other_direction != direction:
                other_exits.update(tiles)
        planning_state = replace(
            planning_state,
            walls=planning_state.walls | other_exits,
        )
        path = bfs_path(planning_state, targets)
        if path is None and shield_through_monsters and state.monsters:
            path = bfs_path(replace(planning_state, monsters=set()), targets)
            if path is not None and len(path) >= 2:
                memory.planned_actions = [ACTION_B] + actions_for_tile_path(path[:2])
                memory.notes["search_plan_kind"] = f"exit:{direction}"
                memory.notes["search_plan_targets"] = tuple(sorted(targets))
                memory.notes["search_plan_room"] = memory.current_room_key
                return memory.planned_actions.pop(0)
        return self.follow(memory, path, f"exit:{direction}", targets)

    def follow(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
        kind: str,
        targets: set[Position],
    ) -> int:
        if path is None or len(path) < 2:
            return ACTION_NOOP
        memory.planned_actions = actions_for_tile_path(path[:2])
        memory.notes["search_plan_kind"] = kind
        memory.notes["search_plan_targets"] = tuple(sorted(targets))
        memory.notes["search_plan_room"] = memory.current_room_key
        action = memory.planned_actions.pop(0)
        memory.notes["search_last_move"] = action
        return action

    def interact(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        targets: set[Position],
        kind: str,
        *,
        avoid_monsters: bool = False,
        shield_through_monsters: bool = False,
    ) -> int:
        if adjacent_target(state.player, targets) is not None:
            memory.planned_actions.clear()
            return ACTION_A
        planning_state = self._planning_state(
            state, memory, avoid_monsters=avoid_monsters
        )
        path = bfs_path_to_adjacent_target(planning_state, targets)
        if path is None and shield_through_monsters and state.monsters:
            path = bfs_path_to_adjacent_target(
                replace(planning_state, monsters=set()), targets
            )
            if path is not None and len(path) >= 2:
                memory.planned_actions = [ACTION_B] + actions_for_tile_path(path[:2])
                memory.notes["search_plan_kind"] = kind
                memory.notes["search_plan_targets"] = tuple(sorted(targets))
                memory.notes["search_plan_room"] = memory.current_room_key
                return memory.planned_actions.pop(0)
        return self.follow(memory, path, kind, targets)

    def _avoid_monsters(self, state: SymbolicState) -> SymbolicState:
        danger: set[Position] = set()
        for mx, my in state.monsters:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    if abs(dx) + abs(dy) <= 1:
                        danger.add((mx + dx, my + dy))
        danger.discard(state.player)
        return replace(state, walls=state.walls | danger)

    def attack(self, state: SymbolicState, memory: AgentMemory) -> int:
        target = adjacent_target(state.player, state.monsters)
        if target is not None and state.player is not None:
            memory.planned_actions = [ACTION_A]
            memory.notes["search_plan_kind"] = "attack"
            memory.notes["search_plan_room"] = memory.current_room_key
            return face_target(state.player, target)
        if state.player is not None and state.monsters:
            px, py = state.player
            nearest = min(
                state.monsters,
                key=lambda pos: abs(px - pos[0]) + abs(py - pos[1]),
            )
            distance = abs(px - nearest[0]) + abs(py - nearest[1])
            if distance <= 3:
                dx, dy = nearest[0] - px, nearest[1] - py
                if abs(dx) >= abs(dy) and dx:
                    advance = ACTION_RIGHT if dx > 0 else ACTION_LEFT
                else:
                    advance = ACTION_DOWN if dy > 0 else ACTION_UP
                memory.planned_actions = [advance] * 8 + [ACTION_A] * 8
                memory.notes["search_plan_kind"] = "attack"
                memory.notes["search_plan_room"] = memory.current_room_key
                return memory.planned_actions.pop(0)
        return self.follow(
            memory,
            bfs_path_to_adjacent_target(state, state.monsters),
            "monster",
            set(state.monsters),
        )

    def clear_stale_plan(self, state: SymbolicState, memory: AgentMemory) -> None:
        if memory.notes.get("search_plan_room") != memory.current_room_key:
            memory.planned_actions.clear()
        kind = str(memory.notes.get("search_plan_kind", ""))
        planned = memory.notes.get("search_plan_targets")
        current = None
        if kind == "chest":
            current = tuple(sorted(state.chests - state.opened_chests))
        elif kind == "monster":
            current = tuple(sorted(state.monsters))
        elif kind == "button":
            current = tuple(sorted(state.buttons))
            if planned and not current:
                memory.button_history.update(planned)
        elif kind == "switch":
            current = tuple(sorted(state.switches))
        if current is not None and planned is not None and current != planned:
            memory.planned_actions.clear()

    def room_has_switch(self, memory: AgentMemory, room: str) -> bool:
        return bool(self._rooms(memory).get(room, {}).get("switches"))

    def room_has_bridge(self, memory: AgentMemory, room: str) -> bool:
        return bool(self._rooms(memory).get(room, {}).get("bridge_signatures"))

    def clear_exit_attempts(self, memory: AgentMemory) -> None:
        self._tried(memory).clear()


class Task4Controller:
    """Search each bridge configuration instead of assuming fixed rooms."""

    def __init__(self) -> None:
        self.explorer = RoomExplorer()

    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _has_sword(self, state: SymbolicState) -> bool:
        return (
            "sword" in state.items
            or "sword" in state.tools
            or state.equipped.get("A") == "sword"
        )

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        room = self.explorer.update(state, memory)
        self.explorer.clear_stale_plan(state, memory)
        if memory.planned_actions:
            return memory.planned_actions.pop(0)
        if state.player is None:
            return ACTION_NOOP

        closed_chests = state.chests - state.opened_chests
        if closed_chests:
            return self.explorer.interact(state, memory, closed_chests, "chest")
        if state.monsters and self._has_sword(state):
            return self.explorer.attack(state, memory)

        if memory.notes.get("inspect_bridge"):
            if self.explorer.room_has_bridge(memory, room):
                memory.notes.pop("inspect_bridge", None)
            else:
                direction = self.explorer.direction_toward(
                    memory,
                    lambda candidate: self.explorer.room_has_bridge(
                        memory, candidate
                    ),
                )
                if direction is not None:
                    return self.explorer.move_to_exit(state, memory, direction)

        direction = self.explorer.direction_to_frontier(state, memory)
        if direction is not None:
            return self.explorer.move_to_exit(state, memory, direction)

        if self.explorer.room_has_switch(memory, room):
            switches = set(state.switches)
            if adjacent_target(state.player, switches) is not None:
                memory.notes["switch_activations"] = (
                    int(memory.notes.get("switch_activations", 0)) + 1
                )
                memory.notes["inspect_bridge"] = True
                self.explorer.clear_exit_attempts(memory)
                return ACTION_A
            return self.explorer.interact(state, memory, switches, "switch")

        direction = self.explorer.direction_toward(
            memory,
            lambda candidate: self.explorer.room_has_switch(memory, candidate),
        )
        if direction is not None:
            return self.explorer.move_to_exit(state, memory, direction)
        return ACTION_NOOP
