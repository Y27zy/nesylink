from __future__ import annotations

from dataclasses import replace

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

from ..planner import actions_for_tile_path, bfs_path, bfs_path_to_adjacent_target
from ..state import AgentMemory, Position, SymbolicState

W, H = MAP_WIDTH_TILES, MAP_HEIGHT_TILES
BRIDGE_STATES = ("west_to_north", "west_to_east", "west_to_south")
BRIDGE_TILES: dict[str, set[Position]] = {
    "west_to_north": {
        (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
        (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4),
        (4, 0), (5, 0), (4, 1), (5, 1), (4, 2), (5, 2),
    },
    "west_to_east": {(x, y) for y in (3, 4) for x in range(W)},
    "west_to_south": {
        (0, 3), (1, 3), (2, 3), (3, 3), (4, 3), (5, 3),
        (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4),
        (4, 5), (5, 5), (4, 6), (5, 6), (4, 7), (5, 7),
    },
}
SWITCH = {(4, 4)}
GUARDIAN = (4, 4)
EXITS = {
    "west": {(0, 3), (0, 4)},
    "east": {(W - 1, 3), (W - 1, 4)},
    "north": {(3, 0), (4, 0), (5, 0)},
    "south": {(3, 7), (4, 7), (5, 7)},
}
CROSS = {
    "west": ACTION_LEFT,
    "east": ACTION_RIGHT,
    "north": ACTION_UP,
    "south": ACTION_DOWN,
}


class Task4Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def _sig(self, targets: set[Position]) -> tuple[Position, ...]:
        return tuple(sorted(targets))

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
        if d["w"] and d["e"] and d["n"] and d["s"]:
            return "center"
        if sum(d.values()) >= 3 or len(state.bridges) >= 6 or len(state.gaps) >= 20:
            return "center"
        if d["e"] and not d["w"]:
            return "west"
        if d["s"] and not d["w"]:
            return "north"
        if d["w"] and not d["e"]:
            return "east"
        if d["n"]:
            return "south"
        if state.switches:
            return "west"
        return "unknown"

    def _bridge(self, memory: AgentMemory) -> str:
        return str(memory.notes.get("t4bridge", "west_to_north"))

    def _want_bridge(self, state: SymbolicState, memory: AgentMemory) -> str:
        # After the guardian falls, keep the current bridge so the center hub
        # stays walkable while we open the revealed final chest.
        if memory.notes.get("t4guard"):
            return self._bridge(memory)
        if self._sword(state):
            return "west_to_south"
        if state.keys > 0:
            return "west_to_east"
        return "west_to_north"

    def _sword(self, state: SymbolicState) -> bool:
        return (
            "sword" in state.items
            or "sword" in state.tools
            or state.equipped.get("A") == "sword"
        )

    def _plan(self, state: SymbolicState, memory: AgentMemory) -> SymbolicState:
        if self._room(state) != "center":
            return state
        bridges = state.bridges | BRIDGE_TILES.get(self._bridge(memory), set())
        if memory.notes.get("t4guard"):
            # Final chest is on the hub tile; union bridge layouts so adjacent
            # approach squares remain reachable even if vision briefly drifts.
            for tiles in BRIDGE_TILES.values():
                bridges |= tiles
        all_tiles = {(x, y) for x in range(W) for y in range(H)}
        return replace(state, bridges=bridges, gaps=all_tiles - bridges)

    def _enqueue(
        self,
        memory: AgentMemory,
        path: list[Position] | None,
        kind: str,
        targets: set[Position],
    ) -> int | None:
        if not path or len(path) < 2:
            return None
        memory.planned_actions = actions_for_tile_path(path)
        memory.notes["t4k"] = kind
        memory.notes["t4t"] = self._sig(targets)
        return memory.planned_actions.pop(0)

    def _clear_stale(self, state: SymbolicState, memory: AgentMemory) -> None:
        kind = memory.notes.get("t4k")
        planned = memory.notes.get("t4t")
        current: tuple[Position, ...] | None = None
        if kind == "monster":
            current = self._sig(state.monsters)
        elif kind == "chest":
            current = self._sig(state.chests)
        elif kind == "switch":
            current = self._sig(state.switches)
        if current is not None and current != planned:
            memory.planned_actions.clear()
            memory.notes.pop("t4k", None)
            memory.notes.pop("t4t", None)

    def _adjacent(self, player: Position, targets: set[Position]) -> Position | None:
        px, py = player
        for tx, ty in sorted(targets):
            if abs(px - tx) + abs(py - ty) == 1:
                return (tx, ty)
        return None

    def _face(self, player: Position, target: Position) -> int | None:
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

    def _exit_goals(self, state: SymbolicState, direction: str) -> set[Position]:
        axis = 0 if direction in {"west", "east"} else 1
        val = 0 if direction in {"west", "north"} else (W - 1 if direction == "east" else H - 1)
        visible = {p for p in state.exits if p[axis] == val}
        return visible or EXITS[direction]

    def _to_exit(self, state: SymbolicState, memory: AgentMemory, direction: str) -> int:
        if state.player is None:
            return ACTION_NOOP
        goals = self._exit_goals(state, direction)
        if state.player in goals:
            return CROSS[direction]
        action = self._enqueue(
            memory,
            bfs_path(self._plan(state, memory), goals),
            f"{direction}_exit",
            goals,
        )
        return action if action is not None else CROSS[direction]

    def _use(self, state: SymbolicState, memory: AgentMemory, targets: set[Position], kind: str) -> int:
        if state.player is not None and self._adjacent(state.player, targets) is not None:
            return ACTION_A
        action = self._enqueue(
            memory,
            bfs_path_to_adjacent_target(self._plan(state, memory), targets),
            kind,
            targets,
        )
        return action if action is not None else ACTION_A

    def _fight(self, state: SymbolicState, memory: AgentMemory, monsters: set[Position]) -> int:
        if state.player is None or not monsters:
            return ACTION_NOOP
        adj = self._adjacent(state.player, monsters)
        if adj is not None:
            memory.notes["t4attacked"] = True
            memory.notes["t4saw_guardian"] = True
            hits = int(memory.notes.get("t4attack_hits", 0)) + 1
            memory.notes["t4attack_hits"] = hits
            # Guardian has 1 HP; lingering vision detections should not trap us.
            if hits >= 6:
                memory.notes["t4guard"] = True
                memory.planned_actions.clear()
                return ACTION_A
            face = self._face(state.player, adj)
            if face is not None:
                memory.planned_actions = [ACTION_A]
                memory.notes["t4k"] = "monster"
                memory.notes["t4t"] = self._sig(monsters)
                return face
            return ACTION_A
        action = self._enqueue(
            memory,
            bfs_path_to_adjacent_target(self._plan(state, memory), monsters),
            "monster",
            monsters,
        )
        return action if action is not None else ACTION_A

    def _guardian(self, state: SymbolicState, memory: AgentMemory) -> set[Position]:
        room = self._room(state)
        if state.monsters and room == "south":
            memory.notes["t4saw_guardian"] = True
            return set(state.monsters)
        if state.monsters:
            return set(state.monsters)
        # Map fallback only before the first south-room sighting.
        if (
            room == "south"
            and not memory.notes.get("t4saw_guardian")
            and not memory.notes.get("t4guard")
        ):
            return {GUARDIAN}
        return set()

    def _mark_guardian_defeated(self, state: SymbolicState, memory: AgentMemory) -> None:
        if not self._sword(state) or memory.notes.get("t4guard"):
            return
        room = self._room(state)
        if room != "south":
            return
        if state.monsters:
            memory.notes["t4saw_guardian"] = True
            return
        if memory.notes.get("t4saw_guardian") or memory.notes.get("t4attacked"):
            memory.notes["t4guard"] = True


    def _switch_targets(self, state: SymbolicState) -> set[Position]:
        return set(state.switches) or (SWITCH if self._room(state) == "west" else set())

    def _rotate(self, state: SymbolicState, memory: AgentMemory) -> int:
        want = self._want_bridge(state, memory)
        cur = self._bridge(memory)
        if cur == want:
            return ACTION_NOOP
        switches = self._switch_targets(state)
        if switches:
            if state.player is not None and self._adjacent(state.player, switches) is not None:
                presses = (BRIDGE_STATES.index(want) - BRIDGE_STATES.index(cur)) % len(BRIDGE_STATES)
                presses = max(1, presses)
                memory.planned_actions = [ACTION_A] * presses
                memory.notes["t4bridge"] = BRIDGE_STATES[
                    (BRIDGE_STATES.index(cur) + presses) % len(BRIDGE_STATES)
                ]
                return memory.planned_actions.pop(0)
            return self._use(state, memory, switches, "switch")
        memory.notes["t4bridge"] = BRIDGE_STATES[(BRIDGE_STATES.index(cur) + 1) % len(BRIDGE_STATES)]
        return ACTION_A

    def _cross_south(self, state: SymbolicState) -> int:
        if state.player is None:
            return ACTION_NOOP
        px, py = state.player
        if px < 4:
            return ACTION_RIGHT
        if px > 4:
            return ACTION_LEFT
        return ACTION_DOWN

    def _enter_center(self, state: SymbolicState, memory: AgentMemory) -> int:
        memory.planned_actions.clear()
        memory.notes.pop("t4k", None)
        memory.notes.pop("t4t", None)
        if state.player and state.player[0] >= W - 1:
            return ACTION_RIGHT
        return self._to_exit(state, memory, "east")

    def _sync_bridge(self, state: SymbolicState, memory: AgentMemory) -> None:
        if self._room(state) != "center" or not state.bridges:
            return
        b = state.bridges
        if any(x in (4, 5) and y >= 6 for x, y in b):
            memory.notes["t4bridge"] = "west_to_south"
        elif any(x in (4, 5) and y <= 1 for x, y in b):
            memory.notes["t4bridge"] = "west_to_north"
        elif any(x >= 7 and y in (3, 4) for x, y in b):
            memory.notes["t4bridge"] = "west_to_east"

    def _go_south(self, state: SymbolicState, memory: AgentMemory) -> int:
        self._sync_bridge(state, memory)
        room = self._room(state)
        phase = str(memory.notes.get("t4post", "leave_east"))

        if room == "south":
            memory.notes["t4post"] = "kill"
            targets = self._guardian(state, memory)
            if not targets:
                memory.notes["t4guard"] = True
                return self._to_exit(state, memory, "north")
            return self._fight(state, memory, targets)

        if phase == "cross":
            memory.planned_actions.clear()
            if room != "center":
                return self._enter_center(state, memory) if room == "west" else self._to_exit(state, memory, "west")
            return self._cross_south(state)

        if phase == "return":
            memory.planned_actions.clear()
            if room == "center":
                memory.notes["t4post"] = "cross"
                return self._cross_south(state)
            return self._enter_center(state, memory) if room == "west" else self._to_exit(state, memory, "west")

        if phase == "leave_east":
            if room == "east":
                return self._to_exit(state, memory, "west")
            memory.notes["t4post"] = "switch"

        if memory.notes.get("t4post") == "switch":
            if room == "west":
                memory.notes["t4post"] = "press"
            else:
                return self._to_exit(state, memory, "west")

        if memory.notes.get("t4post") == "press":
            if room != "west":
                return self._to_exit(state, memory, "west")
            if self._bridge(memory) == "west_to_south":
                memory.notes["t4post"] = "return"
                return self._enter_center(state, memory)
            return self._rotate(state, memory)

        return self._to_exit(state, memory, "west")

    def _go(
        self,
        state: SymbolicState,
        memory: AgentMemory,
        *,
        bridge: str,
        direction: str,
    ) -> int:
        room = self._room(state)
        if self._bridge(memory) != bridge:
            if room == "west":
                return self._rotate(state, memory)
            if room == "center":
                return self._to_exit(state, memory, "west")
            back = {"north": "south", "south": "north", "east": "west", "west": "east"}
            return self._to_exit(state, memory, back.get(room, "west"))

        if room == "center":
            return self._to_exit(state, memory, direction)
        if room == "west":
            return self._to_exit(state, memory, "east")
        if direction == "north" and room == "north" and state.chests:
            return self._use(state, memory, state.chests, "chest")
        if direction == "east" and room == "east" and state.chests:
            return self._use(state, memory, state.chests, "chest")
        if direction == "south" and room == "south":
            return self._fight(state, memory, self._guardian(state, memory))
        if room in {"north", "south", "east"}:
            return self._to_exit(
                state,
                memory,
                {"north": "south", "south": "north", "east": "west"}[room],
            )
        return self._to_exit(state, memory, direction)

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        self._clear_stale(state, memory)
        if memory.planned_actions:
            return memory.planned_actions.pop(0)

        if state.player is None:
            return ACTION_NOOP

        self._sync_bridge(state, memory)
        room = self._room(state)
        self._mark_guardian_defeated(state, memory)

        if (
            self._sword(state)
            and room == "south"
            and not memory.notes.get("t4guard")
            and self._guardian(state, memory)
        ):
            memory.notes["t4post"] = "kill"
            return self._fight(state, memory, self._guardian(state, memory))

        if memory.notes.get("t4guard"):
            targets = set(state.chests) or {GUARDIAN}
            if room == "south":
                return self._to_exit(state, memory, "north")
            if room == "west":
                return self._to_exit(state, memory, "east")
            if room == "east":
                return self._to_exit(state, memory, "west")
            if room == "north":
                return self._to_exit(state, memory, "south")
            # Face the hub chest before attacking; ACTION_A alone can miss.
            if state.player is not None and self._adjacent(state.player, targets) is not None:
                target = self._adjacent(state.player, targets)
                assert target is not None
                face = self._face(state.player, target)
                if face is not None and not memory.notes.get("t4final_faced"):
                    memory.notes["t4final_faced"] = True
                    memory.planned_actions = [ACTION_A]
                    return face
                memory.notes.pop("t4final_faced", None)
                return ACTION_A
            memory.notes.pop("t4final_faced", None)
            return self._use(state, memory, targets, "chest")

        if self._sword(state) and not memory.notes.get("t4guard"):
            return self._go_south(state, memory)

        if state.keys > 0 and not self._sword(state):
            if state.chests and room == "east":
                return self._use(state, memory, state.chests, "chest")
            return self._go(state, memory, bridge="west_to_east", direction="east")

        if state.keys <= 0:
            if state.chests and room == "north":
                return self._use(state, memory, state.chests, "chest")
            return self._go(state, memory, bridge="west_to_north", direction="north")

        if room == "center":
            return ACTION_NOOP
        return self._to_exit(
            state,
            memory,
            {"west": "east", "north": "south", "south": "north", "east": "west"}.get(
                room, "east"
            ),
        )
