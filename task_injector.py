from __future__ import annotations

from typing import Callable, Iterator

from state import AgentMemory, Position, SymbolicState
from task_graph import TaskGraph

# ═══════════════════════════════════════════════════════════════
# 多房间管理
# ═══════════════════════════════════════════════════════════════
DIRECTIONS = ("north", "east", "south", "west")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
def _exit_direction(pos: Position) -> str | None:
    """判断一个 tile 在房间的哪个边缘。"""
    x, y = pos
    if y == 0:       return "north"
    if y == 7:       return "south"
    if x == 9:       return "east"
    if x == 0:       return "west"
    return None

class RoomMemory:
    def _rooms(self,memory:AgentMemory) -> dict:
        return memory.notes.setdefault("rooms",{})

    def _graph(self,memory:AgentMemory) -> dict:
        return memory.notes.setdefault("room_graph",{})
    
    def record_observation(self, state: SymbolicState, memory: AgentMemory) -> None:
        """每步调用：记录当前房间看到的东西。"""
        room = memory.current_room_key
        if room is None:
            return
        rec = self._rooms(memory).setdefault(room, {"exits": {}, "chests": set()})
        # 记录各方向的出口 tile
        for pos in state.exits:
            d = _exit_direction(pos)
            if d:
                rec["exits"].setdefault(d, set()).add(pos)
        rec["chests"] |= state.chests

    def link_rooms(self, from_room: str, direction: str, memory: AgentMemory) -> str:
        """从 from_room 沿 direction 走出去到了新房间，建立双向边。"""
        graph = self._graph(memory)
        to_room = memory.current_room_key
        if to_room is None:
            to_room = f"room_{len(self._rooms(memory))}"
            memory.current_room_key = to_room
        graph.setdefault(from_room, {})[direction] = to_room
        graph.setdefault(to_room, {})[OPPOSITE[direction]] = from_room
        return to_room

    def direction_to(self, memory: AgentMemory, predicate) -> str | None:
        """BFS 在 room_graph 上找路，返回从当前房间出发的第一步方向。"""
        from planner import bfs_graph_path

        start = memory.current_room_key
        if start is None:
            return None
        path = bfs_graph_path(self._graph(memory), start, predicate)
        if path is None or len(path) < 2:
            return None
        for d, nb in self._graph(memory).get(start, {}).items():
            if nb == path[1]:
                return d
        return None

    def unexplored_exits(self, memory: AgentMemory) -> list[str]:
        """当前房间中尚未走过的出口方向。"""
        room = memory.current_room_key
        if room is None:
            return []
        seen = self._rooms(memory).get(room, {}).get("exits", {})
        linked = self._graph(memory).get(room, {})
        return [d for d in DIRECTIONS if d in seen and d not in linked]
# ═══════════════════════════════════════════════════════════════
# 动作生成器工厂函数
# ═══════════════════════════════════════════════════════════════

from planner import (
    actions_for_tile_path,
    bfs_path,
    bfs_path_to_adjacent_target,
    align_to_tile_center,
)
from nesylink.core.constants import ACTION_A, ACTION_NOOP


def navigate_to(targets: set[Position]) -> Callable[..., Iterator[int | None]]:
    """走到 targets 中任意一个可达位置的相邻格。"""

    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        cur = memory.notes.get("_state", _state)
        if cur is None or cur.player is None:
            yield None
            return
        yield from align_to_tile_center(cur)
        path = bfs_path_to_adjacent_target(cur, targets)
        if path is None:
            yield None
            return
        yield from actions_for_tile_path(path)

    return gen


def navigate_and_interact(targets: set[Position]) -> Callable[..., Iterator[int | None]]:
    """走到 targets 中任意一个的相邻格，然后按 A 交互。"""

    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        cur = memory.notes.get("_state", _state)
        if cur is None or cur.player is None:
            yield None
            return
        yield from align_to_tile_center(cur)
        path = bfs_path_to_adjacent_target(cur, targets)
        if path is None:
            yield None
            return
        yield from actions_for_tile_path(path)
        yield ACTION_A

    return gen

def go_to_room(target_room: str, room_mem: RoomMemory) -> Callable[..., Iterator[int | None]]:
    """前往目标房间：room_graph BFS → 走向出口 → 穿越。"""
    from nesylink.core.constants import ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT

    CROSS = {"north": ACTION_UP, "south": ACTION_DOWN,
             "east": ACTION_RIGHT, "west": ACTION_LEFT}

    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        cur_room = memory.current_room_key
        if cur_room == target_room:
            return  # 已在目标房间，无事可做

        # 1. room_graph BFS 找方向
        direction = room_mem.direction_to(memory, lambda r: r == target_room)
        if direction is None:
            yield None
            return

        # 2. 取该方向的出口 tile
        exits = room_mem._rooms(memory).get(cur_room, {}).get("exits", {}).get(direction, set())
        if not exits:
            yield None
            return

        # 3. BFS 走到出口（读取最新 state）
        cur = memory.notes.get("_state", _state)
        path = bfs_path(cur, exits)
        if path is None:
            yield None
            return
        yield from actions_for_tile_path(path)

        # 4. 穿越出口
        for _ in range(1):
            yield CROSS[direction]

    return gen

def fight_monsters() -> Callable[..., Iterator[int | None]]:
    """每步重新 BFS 逼近当前房间任意怪物，相邻且面向时攻击。

    每次 yield 只产生一个像素动作。怪物位置和存活状态每步从
    memory.notes['_state'] 重新读取，不依赖注入时的快照坐标。
    当 cur.monsters 为空时自动结束。
    """

    from planner import action_from_step, neighbors

    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        # 先对齐到当前 tile 中心，避免从边缘出发导致寻路偏差
        cur: SymbolicState | None = memory.notes.get("_state", _state)
        if cur is not None and cur.player is not None:
            yield from align_to_tile_center(cur)

        while True:
            cur = memory.notes.get("_state")
            if cur is None or cur.player is None:
                yield None
                continue

            player = cur.player
            monsters = cur.monsters  # 每步实时读取，怪物移动也能追踪
            if not monsters:
                return  # 房间内无怪物，任务完成

            # 1. 检查是否已和某个怪物相邻
            adjacent_monster: Position | None = None
            for m in monsters:
                for nb in neighbors(player):
                    if nb == m:
                        adjacent_monster = m
                        break
                if adjacent_monster is not None:
                    break

            if adjacent_monster is not None:
                yield action_from_step(player, adjacent_monster)  # 面向
                yield ACTION_A  # 攻击
                continue
            

            # 2. 不邻接 → BFS 逼近最近的怪物
            path = bfs_path_to_adjacent_target(cur, monsters)
            if memory.notes.get("prev_path"):
                prev_path = memory.notes["prev_path"]
                if prev_path != path:
                    yield from align_to_tile_center(cur)
            else:
                yield from align_to_tile_center(cur)
            memory.notes["prev_path"]=path
            print(path)
            if path is None or len(path) < 2:
                yield None
                continue

            yield action_from_step(path[0], path[1])

    return gen


def use_exit(targets: set[Position]) -> Callable[..., Iterator[int | None]]:
    """走到出口所在 tile，然后离开。"""
    from nesylink.core.constants import ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT
    CROSS = {"north": ACTION_UP, "south": ACTION_DOWN,
             "east": ACTION_RIGHT, "west": ACTION_LEFT}
    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        cur = memory.notes.get("_state", _state)
        if cur is None or cur.player is None:
            print("[DEBUG use_exit] player is None!")
            yield None
            return

        # ── 诊断：打印关键状态 ──
        print(f"[DEBUG use_exit] player={cur.player}, targets={targets}")
        print(f"[DEBUG use_exit] walls={cur.walls}")
        print(f"[DEBUG use_exit] monsters={cur.monsters}")
        print(f"[DEBUG use_exit] exits={cur.exits}")
        print(f"[DEBUG use_exit] exit_types={cur.exit_types}")

        # ── 诊断：ASCII 网格可视化 ──
        print("[DEBUG use_exit] Grid (P=player, T=target, W=wall, M=monster, E=exit, .=floor):")
        for y in range(8):
            row = ""
            for x in range(10):
                p = (x, y)
                if p == cur.player:
                    row += "P"
                elif p in targets:
                    row += "T"
                elif p in cur.walls:
                    row += "W"
                elif p in cur.monsters:
                    row += "M"
                elif p in cur.exits:
                    row += "E"
                else:
                    row += "."
            print(f"  {row}")
        yield from align_to_tile_center(cur)
        path = bfs_path(cur, targets)
        print(f"[DEBUG use_exit] bfs_path result: {path}")
        if path is None:
            print("[DEBUG use_exit] bfs_path returned None!")
            yield None
            return
        print(f"[DEBUG use_exit] path found: {path}")
        yield from actions_for_tile_path(path)
        
        direction = _exit_direction(list(targets)[0])
        for _ in range(1):
            yield CROSS[direction]
        

    return gen

def go_to(target:Position) -> Callable[...,Iterator[int | None]]:
    def gen(_state: SymbolicState, memory: AgentMemory) -> Iterator[int | None]:
        cur = memory.notes.get("_state", _state)
        if cur is None or cur.player is None:
            yield None
            return
        yield from align_to_tile_center(cur)
        path = bfs_path(cur, {target})
        if path is None:
            yield None
            return
        yield from actions_for_tile_path(path)
    return gen

# ═══════════════════════════════════════════════════════════════
# 任务注入器
# ═══════════════════════════════════════════════════════════════


class TaskInjector:

    def reset(self) -> None:
        pass

    def inject(self, graph: TaskGraph, state: SymbolicState, memory: AgentMemory) -> None:
        raise NotImplementedError("子类必须实现 inject()")


class MyTaskInjector(TaskInjector):

    def inject(self, graph: TaskGraph, state: SymbolicState, memory: AgentMemory) -> None:
        room = memory.current_room_key
        for pos in state.chests:
            name = f"open_chest_{room}_{pos}"
            if name not in graph:
                graph.add_task(name, action_gen=navigate_and_interact({pos}),room=room)

        if state.monsters and f"fight_monsters_{room}" not in graph:
            graph.add_task(f"fight_monsters_{room}", action_gen=fight_monsters(),prereqs={"sword"},room=room)

        # 获取当前房间已探索的方向（room_graph 中已有连接的出口）
        room_graph = memory.notes.get("room_graph", {})
        explored_directions = set(room_graph.get(room, {}).keys()) if room else set()

        neighbor:set[Position] = set()
        for pos,etype in state.exit_types.items():
            direct = _exit_direction(pos)
            if direct in explored_directions:
                continue  # 该出口方向已探索过，跳过
            if etype == "exit_locked_key":
                from planner import neighbors
                
                for nb in neighbors(pos):
                    if nb in neighbor:
                        graph.add_task(f"explore_door_{room}_{direct}",action_gen=use_exit({pos,nb}),prereqs={"key"},room=room)
                        neighbor.discard(nb)
                        break

            if etype == "exit_conditional":
                from planner import neighbors

                for nb in neighbors(pos):
                    if nb in neighbor:
                        graph.add_task(f"explore_door_{room}_{direct}",action_gen=use_exit({pos,nb}),prereqs={"low"},room=room)
                        neighbor.discard(nb)
                        break

            if etype == "exit_normal":
                from planner import neighbors

                for nb in neighbors(pos):
                    if nb in neighbor:
                        graph.add_task(f"explore_door_{room}_{direct}",action_gen=use_exit({pos,nb}),room=room)
                        neighbor.discard(nb)
                        break

            neighbor.add(pos)

        
        for pos in state.buttons:
            name = f"press_button_{room}_{pos}"
            if name not in graph:
                graph.add_task(name,action_gen=go_to(pos),room=room)


