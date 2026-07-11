# What A Have Done - 第一阶段记录

## 1. 完成范围

本次完成的是 `分工.png` 中 A 成员第一阶段内容：

- `agent.py`：统一策略入口，负责和 `utils/evaluate_policy.py` 的提交接口对接。
- `controllers/__init__.py`：维护 Task ID 到 controller 的分派逻辑。
- `controllers/task1.py`：Task 1 的策略控制逻辑。
- `controllers/task2.py`：Task 2 的策略控制逻辑。
- 为第二阶段 Lean / 报告整理 Task 1/2 可形式化的策略链条、性质和实验结果。

未做第二阶段的 Lean 证明正文；本文档最后列出可直接形式化的证明切入点。

## 2. `agent.py` 已完成内容

`agent.py` 是最终测评时加载的统一入口，当前支持 `make_policy()` 返回 `Policy` 对象。

### 2.1 入口流程

当前 `Policy` 的调用链为：

```text
evaluate_policy.py
  -> make_policy()
  -> Policy.reset(seed, task_id)
  -> make_controller(task_id)
  -> Policy.act(obs, info)
  -> vision.extract_symbolic_state(obs, memory, inventory=inventory)
  -> controller.act(state, memory)
  -> action
```

### 2.2 合规边界

最终推理时，`agent.py` 不读取隐藏结构化状态，例如：

- 不读取 `info["agent"]`
- 不读取 `info["env"]`
- 不读取 `info["entities"]`
- 不读取 `info["dynamic"]`
- 不读取地图 JSON 真值

`agent.py` 只从 `info` 中读取课程允许使用的显式物品栏字段：

```python
inventory = (info or {}).get("inventory", {})
```

然后把 `obs` 和 `inventory` 交给 `vision.extract_symbolic_state()` 生成 `SymbolicState`。

### 2.3 稳定性处理

- 每次 `reset()` 都重新创建 `AgentMemory(seed=seed, task_id=task_id)`，避免不同 episode 之间共享旧计划。
- 每次 `reset()` 根据当前 `task_id` 重新创建 controller。
- 在 `memory.notes["controller"]` 中记录当前实际使用的 controller 名，便于调试分派是否正确。
- 在 `act()` 中将 controller 输出统一转换为 `int`。
- 如果 controller 输出异常，兜底返回 `ACTION_NOOP`，避免测评脚本因单个 controller 输出格式错误直接崩溃。

## 3. `controllers/__init__.py` 已完成内容

原先的多段 `if task_id == ...` 分派已经整理为字典分派：

```python
_CONTROLLER_BY_TASK = {
    "mathematical_logic/task_1": Task1Controller,
    "mathematical_logic/task_2": Task2Controller,
    "mathematical_logic/task_3": Task3Controller,
    "mathematical_logic/task_4": Task4Controller,
    "mathematical_logic/task_5": Task5Controller,
}
```

`make_controller(task_id)` 只负责：

- 按任务 ID 返回对应 controller。
- 未知任务返回 `BaseController`。

这样 `agent.py` 不需要写任何具体任务逻辑，后续其他成员维护 Task 3/4/5 时也只需保证 controller 符合同一接口：

```python
reset(seed, task_id)
act(state, memory) -> int
```

## 4. `controllers/task1.py` 已完成内容

原 Task 1 是固定像素动作序列；当前已经改为基于 `SymbolicState + planner` 的策略控制器。

### 4.1 阶段记录

控制器通过 `memory.notes["task1_phase"]` 记录当前阶段：

- `waiting_for_vision`：视觉还没有识别到玩家位置。
- `collect_key`：没有钥匙，先去宝箱邻接格并开箱。
- `exit`：已有钥匙，规划到出口。
- `exit_north`：已经在北侧出口/顶边，继续向上跨出房间完成任务。
- `no_action`：没有可执行目标。

### 4.2 策略逻辑

Task 1 的控制流程：

1. 如果 `memory.planned_actions` 非空，优先继续执行旧计划。
2. 如果 `state.player is None`，返回 `ACTION_NOOP` 等待视觉。
3. 如果 `state.keys <= 0` 且识别到 `state.chests`：
   - 调用 `bfs_path_to_adjacent_target(state, state.chests)`。
   - 规划到宝箱邻接安全格。
   - 到达邻接格后执行 `ACTION_A` 开箱。
4. 如果 `state.keys > 0` 且识别到 `state.exits`：
   - 调用 `bfs_path(state, state.exits)`。
   - 规划到出口 tile。
   - 如果已经站在出口 tile 上，继续输出 `ACTION_UP` 触发北侧离开。
5. 如果有钥匙且玩家已经位于顶边 `y = 0`，继续 `ACTION_UP`。

### 4.3 依赖字段

Task 1 只依赖：

- `state.player`
- `state.chests`
- `state.exits`
- `state.walls`
- `state.keys`
- `memory.planned_actions`
- `memory.notes`

其中 `state.keys` 来自允许使用的 inventory 信息。

## 5. `controllers/task2.py` 已完成内容

Task 2 已实现为基于 `SymbolicState + planner` 的阶段控制器，不再依赖固定路径或隐藏 `info`。

### 5.1 阶段记录

控制器通过 `memory.notes["task2_phase"]` 记录当前阶段：

- `waiting_for_vision`：视觉还没有识别到玩家位置。
- `kill_monster`：当前仍有怪物，优先接近并攻击。
- `collect_key`：怪物已清空，没钥匙时去宝箱邻接格并开箱。
- `exit`：已有钥匙后前往出口。
- `no_action`：没有可执行目标。

### 5.2 策略逻辑

Task 2 的任务链为：

```text
击败怪物 -> 打开宝箱拿钥匙 -> 进入西侧条件出口
```

当前控制流程：

1. 如果 `memory.planned_actions` 非空，优先继续执行旧计划。
2. 如果 `state.player is None`，返回 `ACTION_NOOP`。
3. 如果 `state.monsters` 非空：
   - 调用 `bfs_path_to_adjacent_target(state, state.monsters)`。
   - 规划到怪物邻接安全格。
   - 到达邻接格后执行 `ACTION_A` 攻击。
4. 如果 `state.keys <= 0` 且识别到 `state.chests`：
   - 调用 `bfs_path_to_adjacent_target(state, state.chests)`。
   - 规划到宝箱邻接安全格。
   - 到达邻接格后执行 `ACTION_A` 开箱。
5. 如果 `state.keys > 0` 且识别到 `state.exits`：
   - 调用 `bfs_path(state, state.exits)`。
   - 规划到出口 tile。

### 5.3 依赖字段

Task 2 只依赖：

- `state.player`
- `state.monsters`
- `state.chests`
- `state.exits`
- `state.walls`
- `state.traps`
- `state.gaps`
- `state.bridges`
- `state.keys`
- `memory.planned_actions`
- `memory.notes`

不读取隐藏房间 ID、实体真值或地图 JSON。

## 6. 与 B/C/D/E 的接口关系

### 6.1 与 B/C 视觉抽象

A 的 controller 不直接处理 raw pixels。统一通过：

```python
from vision import extract_symbolic_state
```

获得 `SymbolicState`。

B/C 需要保证以下字段尽量稳定：

- Task 1：`player`、`walls`、`chests`、`exits`
- Task 2：`player`、`walls`、`chests`、`exits`、`monsters`、`traps`

如果 `state.player is None`，A 的 controller 会等待，不会崩溃。

### 6.2 与 D planner

A 的 Task 1/2 controller 复用 D 提供的 planner 接口：

- `bfs_path(state, goals)`：规划到可站上去的目标，例如出口。
- `bfs_path_to_adjacent_target(state, targets)`：规划到交互目标邻接格，例如宝箱、怪物。
- `actions_for_tile_path(path)`：把 tile 路径转换为像素控制动作序列。

### 6.3 与 E controller

A 维护的入口和 controller 分派逻辑已经包含 Task 4/5：

- `mathematical_logic/task_4 -> Task4Controller`
- `mathematical_logic/task_5 -> Task5Controller`

因此 E 的 controller 可以直接通过同一 `agent.py` 入口进行测评。

## 7. 已验证内容

### 7.1 单任务评估

Task 1：

```bash
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_1 --num-envs 1
```

结果：

```text
mathematical_logic/task_1 seed=0 success=True steps=290 reward=127.050
success_rate: 1.000
avg_steps: 290.0
avg_reward: 127.050
```

Task 2：

```bash
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_2 --num-envs 1
```

结果：

```text
mathematical_logic/task_2 seed=0 success=True steps=332 reward=161.680
success_rate: 1.000
avg_steps: 332.0
avg_reward: 161.680
```

### 7.2 多 seed 回归

```bash
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_1 mathematical_logic/task_2 --num-envs 5
```

结果：

```text
mathematical_logic/task_1
  episodes:     5
  success_rate: 1.000
  avg_steps:    290.0
  avg_reward:   127.050

mathematical_logic/task_2
  episodes:     5
  success_rate: 1.000
  avg_steps:    332.0
  avg_reward:   161.680
```

### 7.3 全任务入口联调

pull 后已确认同一 `agent.py` 入口可以调起 Task 1-5 controller，单 seed 结果如下：

```text
task_1 success=True
task_2 success=True
task_3 success=True
task_4 success=True
task_5 success=True
```

说明 A 维护的入口和分派逻辑没有阻塞 D/E 的后续 controller。

## 8. 第二阶段形式化证明准备

第二阶段 Lean 证明可围绕 A 的 Task 1/2 controller 和 D 的 planner 抽象展开。

### 8.1 建议抽象的数据结构

- `Position`：tile 坐标。
- `Action`：`wait | up | down | left | right | attack | shield`。
- `State`：至少包含：
  - `player : Position`
  - `walls : List Position`
  - `traps : List Position`
  - `chests : List Position`
  - `exits : List Position`
  - `monsters : List Position`
  - `gaps : List Position`
  - `bridges : List Position`
  - `keys : Nat`
- `Path`：`List Position`。
- `Plan`：`List Action`。

### 8.2 可直接形式化的谓词

- `inBounds(p)`：位置在 `10 x 8` 房间范围内。
- `adjacent(p, q)`：两个 tile 曼哈顿距离为 1。
- `isSafe(s, p)`：位置在边界内，且不是墙、陷阱、怪物、宝箱、gap。
- `PathSafe(s, path)`：路径上每个 tile 都安全。
- `PathAdjacent(path)`：路径中相邻节点都是相邻 tile。
- `PlannerSound(s, goals, path)`：路径从玩家出发，终点属于目标集合，且安全相邻。

### 8.3 Task 1 证明方向

可证明的性质：

- `Task1KeyFirst`：
  - 当 `keys = 0` 且存在宝箱时，Task 1 controller 的目标是宝箱邻接格。
- `Task1ChestAdjacentSafe`：
  - 规划到宝箱邻接格时，不会把宝箱格本身当成可走目标。
- `Task1ExitAfterKey`：
  - 当 `keys > 0` 且存在出口时，Task 1 controller 进入出口阶段。
- `Task1NorthExitProgress`：
  - 当玩家已经在北侧出口或顶边且 `keys > 0` 时，controller 输出向上动作以触发完成。

整体性质可表述为：

> 在视觉抽象正确、宝箱和出口可达、`ACTION_A` 可打开邻接宝箱的前提下，Task 1 controller 会先拿钥匙，再通过北侧出口完成任务。

### 8.4 Task 2 证明方向

可证明的性质：

- `Task2MonsterPriority`：
  - 当 `monsters` 非空时，controller 优先进入 `kill_monster` 阶段，不会先去宝箱或出口。
- `Task2ChestAfterMonster`：
  - 当 `monsters = []`、`keys = 0`、`chests` 非空时，controller 进入 `collect_key` 阶段。
- `Task2ExitAfterKey`：
  - 当 `keys > 0` 且存在出口时，controller 进入 `exit` 阶段。
- `Task2AdjacentAttackTarget`：
  - 攻击怪物前的移动目标是怪物邻接安全格，而不是怪物所在危险格。
- `Task2AdjacentChestTarget`：
  - 开箱前的移动目标是宝箱邻接安全格，而不是宝箱所在阻挡格。

整体性质可表述为：

> 在视觉抽象正确、怪物可达且可被攻击、宝箱可达且可打开、出口可达的前提下，Task 2 controller 会按“击败怪物 -> 拿钥匙 -> 到出口”的任务链推进。

### 8.5 证明时需要注明的假设

- Lean 证明基于 `SymbolicState` 层，不证明 raw pixel 到符号状态的识别器对所有图像都正确。
- `vision.py` 的正确性由实验和测评结果支持。
- `ACTION_A` 在宝箱邻接格能打开宝箱。
- `ACTION_A` 在怪物邻接且朝向正确时能攻击怪物。
- `TILE_SIZE` 个同方向原子动作可以完成一个 tile 的移动。
- BFS 返回的路径满足 `PlannerSound`。
- 当前 Task 1/2 证明主要覆盖策略链条、安全目标选择和可解释性，不覆盖完整 Python 引擎内部实现。

## 9. 后续建议

- 报告中可把 A 的工作描述为“统一入口 + Task 1/2 可解释 controller”。
- 实验表格使用第 7 节的 `num_envs=5` 结果。
- Lean 侧优先完成 Task 1/2 的策略顺序证明，再和 D 的 planner 安全性证明合并。
- 若时间允许，可把 `docs/Mathematical_logic/examples/KillMonsterFormalization.lean` 中 Task 2 的具体证明迁移到正式 `lean/TaskProofs.lean`。
