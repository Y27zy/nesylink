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
    MAP_HEIGHT_TILES,
    MAP_WIDTH_TILES,
)

from planner import actions_for_tile_path, bfs_path, bfs_path_to_adjacent_target
from state import AgentMemory, Position, SymbolicState

W, H = MAP_WIDTH_TILES, MAP_HEIGHT_TILES
EAST_OUT = {(W - 1, 3), (W - 1, 4)}
WEST_OUT = {(0, 3), (0, 4)}
SOUTH_OUT = {(4, 7), (5, 7)}
NORTH_OUT = {(4, 0), (5, 0)}
START_BTN = {(2, 6)}
HEAL_CHEST = (7, 1)
START_GOLD = (4, 2)
HEAL_TILE = (6, 1)
START_WEST_DANGER = {(7, 4), (7, 6), (5, 4)}
SOUTH_BLOCK = {(1, 5), (6, 6)}

EAST_GATE_BURST = (
    [ACTION_UP] * 32
    + [ACTION_RIGHT] * 32
    + [ACTION_B] * 4
    + [ACTION_A] * 4
    + [ACTION_A] * 4
    + [ACTION_B] * 4
    + [ACTION_A] * 4
    + [ACTION_A] * 4
    + [ACTION_RIGHT] * 32
)
NORTH_CROSS = [ACTION_B] * 8 + [ACTION_UP]
WEST_GOLD_SCRIPT = (
    [ACTION_B] * 8
    + [ACTION_DOWN] * 48
    + actions_for_tile_path(
        [(8, 6), (8, 7), (7, 7), (6, 7), (5, 7), (4, 7), (3, 7), (2, 7)]
    )
    + [ACTION_UP, ACTION_A]
)


class Task5Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _dirs(self, state: SymbolicState) -> dict[str, bool]:
        ex = state.exits
        return {
            "w": any(x == 0 for x, _ in ex),
            "e": any(x == W - 1 for x, _ in ex),
            "n": any(y == 0 for _, y in ex),
            "s": any(y == H - 1 for _, y in ex),
        }

    def _room(self, state: SymbolicState) -> str:
        d = self._dirs(state)
        if d["w"] and d["e"] and d["s"]:
            return "start"
        if d["n"] and not d["w"] and not d["e"]:
            return "south"
        if d["w"] and not d["e"]:
            return "east"
        if d["e"] and not d["w"]:
            return "west"
        return "start"

    def _sig(self, targets: set[Position]) -> tuple[Position, ...]:
        return tuple(sorted(targets))

    def _plan(self, state: SymbolicState, blocked: set[Position] | None = None) -> SymbolicState:
        if not blocked:
            return state
        return replace(state, walls=state.walls | blocked)

    def _follow(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
        kind: str,
        targets: set[Position],
    ) -> int | None:
        if not path or len(path) < 2:
            return None
        memory.planned_actions = actions_for_tile_path(path)
        memory.notes["t5k"] = kind
        memory.notes["t5t"] = self._sig(targets)
        return memory.planned_actions.pop(0)

    def _clear_stale(self, state: SymbolicState, memory: AgentMemory) -> None:
        if memory.notes.get("t5script"):
            return
        kind = memory.notes.get("t5k")
        planned = memory.notes.get("t5t")
        if kind == "chest" and planned is not None and self._sig(state.chests) != planned:
            memory.planned_actions.clear()
            memory.notes.pop("t5k", None)
            memory.notes.pop("t5t", None)
        if kind == "south_exit" and state.keys > 0:
            memory.planned_actions.clear()
            memory.notes.pop("t5k", None)
            memory.notes.pop("t5t", None)

    def _on_room_change(self, memory: AgentMemory, room: str) -> None:
        prev = memory.notes.get("t5prev")
        if prev == room:
            return
        memory.notes["t5prev"] = room
        if memory.notes.get("t5script"):
            return
        memory.planned_actions.clear()
        memory.notes.pop("t5k", None)
        memory.notes.pop("t5t", None)

    def _cross(self, pos: Position, direction: str) -> int | None:
        exits = {
            "west": WEST_OUT,
            "east": EAST_OUT,
            "south": SOUTH_OUT,
            "north": NORTH_OUT,
        }[direction]
        if pos not in exits:
            return None
        return {
            "west": ACTION_LEFT,
            "east": ACTION_RIGHT,
            "south": ACTION_DOWN,
            "north": ACTION_UP,
        }[direction]

    def _nav_block(self, state: SymbolicState, direction: str = "") -> set[Position] | None:
        if self._room(state) == "start" and direction == "west":
            return set(START_WEST_DANGER)
        return None

    def _south_block(self, state: SymbolicState) -> set[Position]:
        return set(SOUTH_BLOCK) | set(state.monsters)

    def _to_exit(self, state: SymbolicState, memory: AgentMemory, direction: str) -> int:
        if state.player is None:
            return ACTION_NOOP
        step = self._cross(state.player, direction)
        if step is not None:
            if direction == "north" and self._room(state) == "south":
                return self._script(memory, "ncross", list(NORTH_CROSS))
            return step
        goals = {
            "west": WEST_OUT,
            "east": EAST_OUT,
            "south": SOUTH_OUT,
            "north": NORTH_OUT,
        }[direction]
        blocked = self._nav_block(state, direction)
        action = self._follow(
            memory,
            bfs_path(self._plan(state, blocked), goals),
            f"{direction}_exit",
            goals,
        )
        return action if action is not None else ACTION_NOOP

    def _walk(self, state: SymbolicState, memory: AgentMemory, targets: set[Position], kind: str) -> int:
        if state.player is None or state.player in targets:
            return ACTION_NOOP
        blocked = self._south_block(state) if self._room(state) == "south" else None
        action = self._follow(
            memory,
            bfs_path(self._plan(state, blocked), targets),
            kind,
            targets,
        )
        return action if action is not None else ACTION_NOOP

    def _adjacent(self, state: SymbolicState, targets: set[Position]) -> bool:
        if state.player is None:
            return False
        px, py = state.player
        return any(abs(px - tx) + abs(py - ty) == 1 for tx, ty in targets)

    def _face(self, player: Position, target: Position) -> int:
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

    def _open(self, state: SymbolicState, memory: AgentMemory, targets: set[Position]) -> int:
        if self._adjacent(state, targets):
            if START_GOLD in targets:
                memory.notes["t5sgold"] = True
            return ACTION_A
        room = self._room(state)
        if room == "start":
            blocked = self._nav_block(state, "west")
        elif room == "south":
            blocked = self._south_block(state)
        else:
            blocked = None
        action = self._follow(
            memory,
            bfs_path_to_adjacent_target(self._plan(state, blocked), targets),
            "chest",
            targets,
        )
        return action if action is not None else ACTION_A

    def _open_heal(self, state: SymbolicState, memory: AgentMemory) -> int:
        if self._adjacent(state, {HEAL_CHEST}):
            memory.notes["t5healed"] = True
            return ACTION_A
        if state.player == HEAL_TILE:
            memory.planned_actions = [self._face(state.player, HEAL_CHEST), ACTION_A]
            memory.notes["t5healgo"] = True
            return memory.planned_actions.pop(0)
        action = self._follow(memory, bfs_path(state, {HEAL_TILE}), "heal", {HEAL_TILE})
        return action if action is not None else ACTION_NOOP

    def _script(self, memory: AgentMemory, name: str, actions: list[int]) -> int:
        memory.planned_actions = list(actions)
        memory.notes["t5script"] = name
        return memory.planned_actions.pop(0)

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        self._clear_stale(state, memory)
        room = self._room(state)
        self._on_room_change(memory, room)

        if memory.planned_actions:
            action = memory.planned_actions.pop(0)
            if not memory.planned_actions:
                script = memory.notes.pop("t5script", None)
                if script == "ncross":
                    memory.notes.pop("t5k", None)
                    memory.notes.pop("t5t", None)
                if script == "gate":
                    memory.notes["t5gate"] = True
                if script == "wenter":
                    memory.notes["t5wgold"] = True
                if memory.notes.pop("t5healgo", None):
                    memory.notes["t5healed"] = True
            return action

        if state.player is None:
            return ACTION_NOOP

        if state.keys > 0:
            memory.notes["t5key"] = True

        if not memory.notes.get("t5btn"):
            targets = set(state.buttons) or START_BTN
            if state.player in targets:
                wait = int(memory.notes.get("t5wait", 1))
                memory.notes["t5wait"] = wait - 1
                if wait <= 1:
                    memory.notes["t5btn"] = True
                return ACTION_NOOP
            return self._walk(state, memory, targets, "button")

        if not memory.notes.get("t5key"):
            if room == "south":
                if state.chests:
                    return self._open(state, memory, state.chests)
                if state.player in NORTH_OUT:
                    return self._script(memory, "ncross", list(NORTH_CROSS))
                action = self._follow(
                    memory,
                    bfs_path(self._plan(state, self._south_block(state)), NORTH_OUT),
                    "north_exit",
                    NORTH_OUT,
                )
                return action if action is not None else self._to_exit(state, memory, "north")
            return self._to_exit(state, memory, "south")

        if not memory.notes.get("t5healed"):
            if room == "east":
                if HEAL_CHEST in state.chests:
                    return self._open_heal(state, memory)
                return self._to_exit(state, memory, "west")
            if room == "start":
                if not memory.notes.get("t5gate"):
                    return self._script(memory, "gate", list(EAST_GATE_BURST))
                return self._to_exit(state, memory, "east")
            if room == "south":
                return self._to_exit(state, memory, "north")
            return self._to_exit(state, memory, "east")

        if not memory.notes.get("t5sgold"):
            if room == "start":
                if START_GOLD in state.chests:
                    return self._open(state, memory, {START_GOLD})
                memory.notes["t5sgold"] = True
            elif room == "west":
                return self._to_exit(state, memory, "east")
            elif room == "east":
                return self._to_exit(state, memory, "west")
            else:
                return self._to_exit(state, memory, "north")

        if not memory.notes.get("t5wgold"):
            if room == "west":
                return self._script(memory, "wenter", list(WEST_GOLD_SCRIPT))
            if room == "east":
                return self._to_exit(state, memory, "west")
            if room == "start":
                return self._to_exit(state, memory, "west")
            return self._to_exit(state, memory, "north")

        return ACTION_NOOP
