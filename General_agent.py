from __future__ import annotations

from typing import Any, Iterator

from nesylink.core.constants import ACTION_NOOP
from state import AgentMemory, SymbolicState
from task_graph import TaskGraph, TaskNode
from task_injector import MyTaskInjector,RoomMemory
from vision import extract_symbolic_state


class Policy:
    """通用策略入口 —— 使用任务依赖 DAG + 动态注入替代硬编码 controller。

    由 utils/evaluate_policy.py 加载。
    """

    def __init__(self) -> None:
        self.task_id: str | None = None
        self.memory = AgentMemory()
        self.graph = TaskGraph()
        self.injector = MyTaskInjector()
        self.room_mem = RoomMemory()
        
        # 当前正在执行的任务及其动作迭代器
        self._current_task: TaskNode | None = None
        self._action_iter: Iterator[int | None] | None = None
        self._room_action_iter: Iterator[int | None] | None = None

    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        self.task_id = task_id
        self.memory = AgentMemory(seed=seed, task_id=task_id)

        # 清空图并重置注入器
        self.graph._tasks.clear()
        self.injector.reset()

        self.need_change_room = False
        self._current_task = None
        self._action_iter = None
        self._room_action_iter=None

    def act(self, obs: Any, info: dict[str, Any] | None = None) -> int:
        inventory = (info or {}).get("inventory", {})
        state = extract_symbolic_state(obs, self.memory, inventory=inventory)
        print(state.raw_features["dynamic_objects"])
        print(state.opened_chests)
        print(self.graph._tasks)

        # ── 检测房间切换：比较上一步 _state 与当前 state 的 player 位置 ──
        prev_state: SymbolicState | None = self.memory.notes.get("_state")
        if (
            prev_state is not None
            and prev_state.player is not None
            and state.player is not None
        ):
            px, py = prev_state.player
            cx, cy = state.player
            # 如果位置发生非相邻跳跃（曼哈顿距离 > 1），说明切换了房间
            if abs(cx - px) > 1 or abs(cy - py) > 1:
                # 根据跳跃方向判断穿越了哪个出口
                if py <= 1 and cy >= 6:
                    direction = "north"
                elif py >= 6 and cy <= 1:
                    direction = "south"
                elif px <= 1 and cx >= 8:
                    direction = "west"
                elif px >= 8 and cx <= 1:
                    direction = "east"
                else:
                    direction = None

                if direction is not None:
                    old_room = self.memory.current_room_key
                    # 检查 room_graph 中是否已有该方向的记录
                    graph = self.room_mem._graph(self.memory)
                    if old_room is not None and direction in graph.get(old_room, {}):
                        # 已有记录 → 直接使用
                        new_room = graph[old_room][direction]
                    else:
                        # 新房间 → 生成 key
                        counter = self.memory.notes.get("_room_counter", 0)
                        new_room = f"room_{counter}"
                        self.memory.notes["_room_counter"] = counter + 1
                    self.memory.current_room_key = new_room
                    if old_room is not None:
                        self.room_mem.link_rooms(old_room, direction, self.memory)
                    print(f"[ROOM SWITCH] {old_room} → {new_room} (direction: {direction})")

        self.memory.notes["_state"] = state
        if self.memory.current_room_key is None:
            self.memory.current_room_key = "room_0"
            self.memory.notes["_room_counter"] = 1  # room_0 已占用，新房间从 room_1 开始
        room_key = self.memory.current_room_key
        # 每步记录当前房间的出口 / 宝箱位置，供跨房间寻路使用
        self.room_mem.record_observation(state, self.memory)
        print(room_key)
        if self.memory.notes.get(room_key) is None:
        # ── 第一步：观察世界，动态注入任务 ──────────────
            self.injector.inject(self.graph, state, self.memory)
            self.memory.notes[room_key]=True

        if self._room_action_iter is not None:
            try:
                action = next(self._room_action_iter)
                if action is not None:
                    return action
                return ACTION_NOOP
            except StopIteration:
                self._room_action_iter = None
                # 穿越完成，检查是否到达目标房间
                if self._current_task is not None and self._current_task.room != room_key:
                    # 还没到 → 继续寻路（可能中间经过多个房间）
                    from task_injector import go_to_room
                    self._room_action_iter = go_to_room(
                        self._current_task.room, self.room_mem
                    )(state, self.memory)
                    # 重新进入本 if 分支消费第一个动作
                    return self.act(obs, info)  # 递归调用，走一遍新逻辑

        # ── 第二步：如果当前有正在执行的任务，继续消费动作 ──
        if self._action_iter is not None:
            try:
                action = next(self._action_iter)
                if action is not None:
                    return action
                # action is None → 本轮无法行动，返回 NOOP 保持当前任务
                return ACTION_NOOP
            except StopIteration:
                # 动作序列耗尽 → 标记当前任务完成，释放后继
               
                if self._current_task is not None:
                    self.graph.remove_task(self._current_task.name)
                self._current_task = None
                self._action_iter = None

        # ── 第三步：选取一个合法的任务 ──────────────
        task = self.graph._tasks
        legal_task: dict[str, TaskNode] = {}
        if task is None:
            return ACTION_NOOP
        for key,node in task.items():
            legal:bool = True
            for p in node.prereqs:
                if p =="key" and state.keys==0:
                    legal=False
                elif p=="sword" and "sword" not in state.tools:
                    legal=False
                elif p=="low" and len(task)>1:
                    legal=False
            if legal:
                legal_task[key]=node
        # 优先选取当前房间的击杀怪物任务
        for key, node in legal_task.items():
            if "fight_monsters" in key and node.room == room_key:
                self._current_task = node
                self._action_iter = node.action_gen(state, self.memory)
                break
        # 若未选中，按原逻辑选取第一个当前房间的任务
        if self._current_task is None:
            for key, node in legal_task.items():
                self._current_task = node
                self._action_iter = node.action_gen(state, self.memory)
                if node.room == room_key:
                    break
        
        #__若不在任务同一房间
        if self._current_task.room != room_key:
            from task_injector import go_to_room
            self._room_action_iter = go_to_room(
                self._current_task.room, self.room_mem
            )(state, self.memory)
            # 跳过下面"第四步"直接递归进入房间导航分支
            return self.act(obs, info)


        # ── 第四步：产出第一个动作 ──────────────────────
        try:
            action = next(self._action_iter)
            if action is not None:
                return action
            return ACTION_NOOP
        except StopIteration:
            # 任务的动作生成器一启动就结束了 → 直接标记完成，下步再选
            self.graph.remove(task.name)
            self._current_task = None
            self._action_iter = None
            return ACTION_NOOP


def make_policy() -> Policy:
    return Policy()
