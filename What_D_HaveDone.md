# What D Have Done - 第一阶段记录

## 1. 完成范围

本次完成的是 `分工.png` 中 D 成员第一阶段内容：

- `planner.py`：tile 级路径规划、安全格判断、目标邻接格、tile 路径到原子动作的转换。
- `controllers/task3.py`：Task 3 的策略控制逻辑。
- 为第二阶段 Lean / 报告整理可形式化的定义、性质和证明切入点。

未做第二阶段的 Lean 证明正文；本文档最后已经列出证明准备。

## 2. `planner.py` 已完成内容

- 将地图边界从硬编码 `10 x 8` 改为引用环境常量：
  - `MAP_WIDTH_TILES`
  - `MAP_HEIGHT_TILES`
- 保留并完善 BFS 相关接口：
  - `in_bounds(pos)`：判断 tile 坐标是否在地图内。
  - `neighbors(pos)`：按上、下、左、右枚举相邻 tile。
  - `is_safe_tile(state, pos)`：判断 tile 是否可通行。
  - `action_from_step(current, nxt)`：把相邻 tile 的一步移动转换为动作。
  - `bfs_path(state, goals)`：从玩家当前位置搜索到目标集合的最短路径。
  - `adjacent_goal_tiles(state, targets)`：把交互目标转换为可站立的邻接格集合。
  - `bfs_path_to_adjacent_target(state, targets)`：搜索到目标邻接格。
  - `actions_for_tile_path(path)`：把 tile 路径转换为像素控制下的原子动作序列。
- 完善安全格规则：
  - 墙、怪物、未开启宝箱默认不可走。
  - 陷阱、gap 默认不可走。
  - bridge 优先于 trap/gap：如果某格被识别为 bridge，则允许作为可通行格处理。
- 将 tile 步长从硬编码 `16` 改为引用 `TILE_SIZE`，方便后续形式化时把“每个 tile 对应多少原子动作”作为环境常量。

## 3. `controllers/task3.py` 已完成内容

原文件只有 `ACTION_NOOP` 占位；现在已经实现 Task 3 的阶段控制器。

### 3.1 阶段记录

控制器通过 `memory.notes["task3_phase"]` 记录当前阶段，便于调试和报告说明：

- `waiting_for_vision`：当前视觉抽象还没有给出玩家位置。
- `go_west_to_key_room`：还没有钥匙、没有可交互目标时，向西推进。
- `handle_monster`：当前房间识别到怪物，先接近怪物邻接格并攻击。
- `open_key_chest`：当前房间识别到宝箱，先走到宝箱邻接格并交互。
- `waiting_for_key_update`：疑似已经打开钥匙房宝箱，但 inventory 还没有更新钥匙数。
- `return_east_to_start_or_exit`：拿到钥匙后持续向东，依次返回怪物房、起点房，最后打开东侧锁门。

### 3.2 路径与动作执行

- 增加 `_follow_or_plan(memory, path)`：
  - BFS 成功时把 tile 路径转换成原子动作并存入 `memory.planned_actions`。
  - 每次只弹出一个 action，保持和 `Task2Controller` 的执行方式一致。
- 增加计划签名校验：
  - 怪物目标集合变化时，清空旧计划并重新规划。
  - 宝箱目标集合变化时，清空旧计划并重新规划。
  - 拿到钥匙后，清空仍在执行的西行计划。
  - 面向怪物后排队的单步 `ACTION_A` 标记为 `attack`，避免被移动怪物的位置变化误清掉。
- 增加东西向出口目标：
  - 西侧出口目标：`(0, 3)`、`(0, 4)`。
  - 东侧出口目标：`(MAP_WIDTH_TILES - 1, 3)`、`(MAP_WIDTH_TILES - 1, 4)`。
  - 如果视觉识别到了 `state.exits`，优先使用可见出口；否则使用固定边界出口作为兜底。
- 增加 `_move_to_exit(state, memory, direction)`：
  - 先 BFS 到对应方向出口 tile。
  - 如果已经站在出口 tile 上，则继续输出对应方向动作触发房间切换。
  - 如果 BFS 暂时失败，则用方向动作兜底，避免直接停住。

### 3.3 怪物、宝箱和钥匙策略

- 怪物处理：
  - 如果 `state.monsters` 非空，优先进入 `handle_monster`。
  - 不在邻接格时，调用 `bfs_path_to_adjacent_target()` 规划到怪物邻接格。
  - 已在邻接格时，先输出面向怪物的移动动作，再排队一个 `ACTION_A`，提高剑攻击命中的概率。
- 宝箱处理：
  - 如果 `state.chests` 非空，进入 `open_key_chest`。
  - 不在邻接格时，规划到宝箱邻接格。
  - 已在邻接格时，直接执行 `ACTION_A` 开箱。
- 拿到钥匙后：
  - 使用 `state.keys > 0` 作为返回阶段的唯一关键条件。
  - 不依赖房间 id；只要有钥匙就持续向东推进，符合 Task 3 地图的顺序：钥匙房 -> 怪物房 -> 起点房 -> 东侧锁门完成。

## 4. 与 B/C 视觉抽象的接口

D 的代码不读取最终推理禁用的隐藏结构化字段，例如：

- 不读取 `info["agent"]`
- 不读取 `info["env"]`
- 不读取 `info["entities"]`
- 不读取房间 id

controller 只依赖 `SymbolicState` / `AgentMemory` 中的字段：

- `state.player`
- `state.walls`
- `state.chests`
- `state.exits`
- `state.monsters`
- `state.traps`
- `state.gaps`
- `state.bridges`
- `state.keys`
- `memory.planned_actions`
- `memory.notes`

因此 B/C 只要把 raw pixels 稳定抽象成上述 tile 集合，D 的 planner 和 Task 3 controller 就可以接上。

## 5. 已验证内容

- 已运行静态编译检查：

```bash
python -m py_compile planner.py controllers/task3.py
```

结果：通过。

- 已安装项目运行依赖：

```bash
python -m pip install -e .
```

- 已运行轻量符号态 smoke test：

```bash
python -c "..."
```

结果：通过。该测试构造了带有玩家、出口、怪物、宝箱、钥匙的 `SymbolicState`，确认 Task 3 controller 在符号输入正确时会按预期输出西行、攻击、开箱、东返动作。

- 已运行 Task 3 单环境端到端评估：

```bash
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 1
```

结果：

```text
mathematical_logic/task_3 seed=0 success=False steps=1500 reward=-15.000
monster_killed: 0.000
key_collected: 0.000
```

原因分析：当前 `vision.py` 仍是占位实现，没有从 pixels 中抽取 `state.player`、`state.monsters`、`state.chests`、`state.exits` 等 tile 级字段。D 的 controller 在拿不到玩家位置时会进入 `waiting_for_vision`，因此端到端评估无法推进。需要等待 B/C 完成视觉抽象后再重跑。

后续建议验证命令：

```bash
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 1
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 10
python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_2 --num-envs 5
```

## 6. 第二阶段形式化证明准备

第二阶段可以围绕以下 Python 实现抽象 Lean 定义和定理。

### 6.1 建议抽象的数据结构

- `Position`：可形式化为 `(Nat × Nat)` 或带边界证明的坐标。
- `Action`：枚举 `up | down | left | right | interact | wait`。
- `State`：至少包含：
  - `player : Option Position`
  - `walls : Finset Position`
  - `monsters : Finset Position`
  - `chests : Finset Position`
  - `traps : Finset Position`
  - `gaps : Finset Position`
  - `bridges : Finset Position`
  - `exits : Finset Position`
  - `keys : Nat`
- `Path`：`List Position`。
- `Plan`：`List Action`。

### 6.2 可直接形式化的谓词

- `InBounds(p)`：
  - 对应 `planner.in_bounds`。
  - 语义：`0 <= p.x < width` 且 `0 <= p.y < height`。
- `Adjacent(p, q)`：
  - 对应 `neighbors` / `action_from_step`。
  - 语义：曼哈顿距离为 1。
- `Safe(s, p)`：
  - 对应 `is_safe_tile`。
  - 语义：在边界内，且不属于墙、怪物、宝箱、非桥覆盖的陷阱、非桥覆盖的 gap。
- `PathValid(s, path)`：
  - 路径非空时首元素为玩家位置。
  - 路径中每一步相邻。
  - 中间节点满足 `Safe`，目标节点允许属于目标集合。
- `AdjacentGoal(s, target, p)`：
  - `Adjacent(p, target)` 且 `Safe(s, p)`。
- `ActionsFollowPath(path, actions)`：
  - 对应 `actions_for_tile_path`。
  - 每个相邻 tile step 转成 `TILE_SIZE` 个同方向原子动作。

### 6.3 建议证明的核心引理

- `neighbors_sound`：
  - 如果 `q ∈ neighbors(p)`，则 `Adjacent(p, q)`。
- `action_from_step_sound`：
  - 如果 `action_from_step(p, q) = a`，则执行 `a` 的方向与 `p -> q` 一致。
- `actions_for_tile_path_sound`：
  - 如果 `PathValid(s, path)`，则 `actions_for_tile_path(path)` 能按顺序表达该 tile 路径。
- `adjacent_goal_tiles_sound`：
  - 如果 `g ∈ adjacent_goal_tiles(s, targets)`，则存在 `t ∈ targets`，满足 `Adjacent(g, t)` 且 `Safe(s, g)`。
- `bfs_path_sound`：
  - 如果 `bfs_path(s, goals) = some path`，则 `PathValid(s, path)`，且路径终点属于 `goals`。
- `bfs_path_completeness_on_finite_grid`：
  - 在有限网格上，如果存在一条从玩家到目标的安全路径，则 BFS 能找到一条路径。
- `bfs_path_shortest`：
  - BFS 返回的路径长度不大于任意其他安全路径长度。

### 6.4 Task 3 策略正确性证明方向

可以把 Task 3 controller 证明拆成阶段不变量：

- `NoKeyGoWest`：
  - 当 `keys = 0`、没有怪物和宝箱目标时，controller 选择向西出口推进。
- `MonsterPriority`：
  - 当 `monsters` 非空时，controller 优先执行怪物处理，不会先去宝箱或出口。
- `ChestPriorityAfterMonster`：
  - 当 `keys = 0`、`monsters = ∅`、`chests` 非空时，controller 走到宝箱邻接格并交互。
- `HasKeyGoEast`：
  - 当 `keys > 0` 时，controller 总是向东出口推进。
- `NoHiddenInfoDependency`：
  - controller 的决策函数只依赖 `SymbolicState` 和 `AgentMemory`，不依赖隐藏房间 id 或结构化真值信息。

Task 3 的整体正确性可以表述为：

> 在 B/C 视觉抽象正确、地图为 Task 3 固定三房间结构、BFS 对静态障碍返回有效路径、交互动作成功的前提下，D 的 controller 会先处理怪物，再取得钥匙，最后从东侧锁门完成任务。

### 6.5 证明时需要注明的假设

- 视觉抽象正确：`SymbolicState` 中的玩家、出口、怪物、宝箱、障碍集合与当前像素观测一致。
- 动态怪物不会永久破坏可达性；若怪物仍存在，controller 会继续进入 `handle_monster`。
- `ACTION_A` 在宝箱邻接格会打开宝箱。
- `ACTION_A` 在面向怪物且攻击范围覆盖怪物时会造成伤害。
- Task 3 地图结构固定：
  - 起点房有西出口和东侧锁门。
  - 怪物房连接起点房和钥匙房。
  - 钥匙房有宝箱和东出口。
- `TILE_SIZE` 个同方向原子动作可完成相邻 tile 的移动。
