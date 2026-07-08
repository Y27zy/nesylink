# TODO_D - D 成员第一阶段任务清单

> 分工依据：`分工.png` 中 D 的第一阶段负责 `planner.py`，包括 BFS/A*、安全格判断、目标邻接格、tile 路径转换原子动作，并负责 `controllers/task3.py`。
> 本文档只覆盖第一阶段 Agent / 图像抽象相关工作，不包含第二阶段 Lean / 报告。

## 0. 当前代码状态

- [x] `planner.py` 已有基础 BFS：
  - `in_bounds(pos)`
  - `neighbors(pos)`
  - `is_safe_tile(state, pos)`
  - `action_from_step(current, nxt)`
  - `bfs_path(state, goals)`
  - `adjacent_goal_tiles(state, targets)`
  - `bfs_path_to_adjacent_target(state, targets)`
  - `actions_for_tile_path(path)`
- [x] `controllers/task3.py` 已从 `ACTION_NOOP` 占位改为阶段控制器。
- [ ] `vision.py` 还没有稳定输出玩家、墙、宝箱、出口、怪物等 tile 级符号；D 的实现需要兼容 B/C 后续补上的 `SymbolicState`。

## 1. 第一阶段目标

- [x] 让 `planner.py` 提供 Task 3 可复用的 tile 级规划能力。
- [x] 让 `controllers/task3.py` 能完成 Task 3 主流程：
  1. 从 `start_room` 向西进入 `monster_hall`。
  2. 穿过或处理怪物房。
  3. 向西进入 `key_room`。
  4. 走到宝箱邻接格并按 `ACTION_A` 开箱拿钥匙。
  5. 向东返回 `monster_hall`。
  6. 继续向东回到 `start_room`。
  7. 持钥匙从东侧锁门离开，完成任务。
- [x] controller 只依赖 `SymbolicState` 和 `AgentMemory`，不读取隐藏 `info["agent"]`、`info["env"]`、`info["entities"]` 等最终推理禁用字段。

## 2. `planner.py` 待办

- [x] 核对地图边界：
  - `in_bounds()` 已改为引用 `nesylink.core.constants.MAP_WIDTH_TILES` / `MAP_HEIGHT_TILES`。
- [x] 完善安全格判断 `is_safe_tile()`：
  - 墙、陷阱、怪物、未开启宝箱、gap 默认不可走。
  - 出口 tile 应允许作为 BFS 终点。
  - bridge 应在可通行时允许通过。
  - 如 B/C 视觉会把动态 bridge/gap 同时放入集合，需要明确优先级：bridge 可走，gap 不可走。
- [x] 明确“交互目标”的规划方式：
  - 宝箱、怪物、按钮、switch 这类目标通常不能直接走上去，应规划到邻接安全格。
  - 出口/房间边界通常应规划到出口 tile 或房间边界方向上的可达 tile。
- [x] 保留并检查 `bfs_path_to_adjacent_target()`：
  - 输入目标集合为空时返回 `None`。
  - 玩家缺失时返回 `None`。
  - 没有可达邻接格时返回 `None`。
- [x] 检查 `actions_for_tile_path()`：
  - 每移动 1 个 tile 输出 `TILE_SIZE` 个相同方向动作。
  - 空路径或只有当前位置时返回空列表。
  - 非相邻路径 step 抛出 `ValueError`。
- [x] 视时间决定是否加 A*：
  - Task 3 地图较简单，BFS 足够，本阶段未额外加入 A*。

## 3. `controllers/task3.py` 待办

- [x] 参照 `controllers/task2.py` 的模式实现 `_follow_or_plan()`：
  - 如果 `memory.planned_actions` 非空，优先继续执行。
  - 新路径规划成功后写入 `memory.planned_actions`，每次弹出一个 action。
  - 规划失败时返回 `None`，由上层决定等待、交互或兜底动作。
- [x] 设计 Task 3 阶段机，建议存到 `memory.notes["task3_phase"]`：
  - `waiting_for_vision`
  - `go_west_to_key_room`
  - `handle_monster`
  - `open_key_chest`
  - `waiting_for_key_update`
  - `return_east_to_start_or_exit`
- [x] 定义跨房间导航策略：
  - 因为 `SymbolicState` 当前只表示“当前房间”的 tiles，controller 需要在每个房间内朝对应边界移动。
  - 可用玩家位置、出口集合、钥匙数量、宝箱集合、怪物集合判断当前阶段。
  - 若视觉暂时无法区分房间，可用阶段机和钥匙数量推断下一步方向。
- [x] 怪物房策略：
  - 如果 `state.monsters` 非空，优先规划到怪物邻接格并按 `ACTION_A` 攻击。
  - 如果怪物挡路但可绕行，可先让 planner 规划到西侧出口或边界。
  - 攻击后清空旧计划，等待下一帧视觉确认怪物是否还在。
- [x] 钥匙房策略：
  - `state.keys <= 0` 且 `state.chests` 非空时，规划到宝箱邻接格。
  - 到达邻接格后执行 `ACTION_A`。
  - 检测到 `state.keys > 0` 后切换到返回阶段。
- [x] 返回与开门策略：
  - `state.keys > 0` 后持续向东规划/移动，直到回到起点房间东侧锁门。
  - 如果能看到 `state.exits`，优先规划到出口。
  - 如果看不到出口但阶段明确，可向对应方向输出一段移动动作作为兜底。
- [x] 处理计划失效：
  - 怪物/宝箱目标集合变化、拿到钥匙后，会丢弃旧计划并重新规划。
  - 规划结果为空但已在目标邻接格时，直接交互或移动到下一阶段。

## 4. 与 B/C 视觉抽象的接口约定

- [x] D 需要的最小字段：
  - `state.player`
  - `state.walls`
  - `state.chests`
  - `state.exits`
  - `state.monsters`
  - `state.traps`
  - `state.gaps`
  - `state.bridges`
  - `state.keys`
- [x] 坐标必须是 tile 坐标 `(x, y)`，范围 `x=0..9`、`y=0..7`。
- [x] `state.keys` 可以来自允许使用的 inventory 字段；controller 用它判断是否已经拿到钥匙。
- [x] 如果 B/C 暂时不能稳定识别出口，D 需要在 Task 3 中提供方向兜底：
  - 去钥匙：向西。
  - 返回起点：向东。
  - 最终开门：向东。

## 5. 本地验证清单

- [x] 静态检查：
  - `python -m py_compile planner.py controllers/task3.py`
- [ ] 单任务评估：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 1`
- [ ] 多 seed 评估：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 10`
- [ ] 回归确认 Task 2 没被 planner 改坏：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_2 --num-envs 5`
- [ ] 观察失败日志时重点看：
  - `memory.notes["task3_phase"]` 是否按预期推进。
  - 是否卡在房间边界。
  - 是否反复对空位置按 `ACTION_A`。
  - 是否把宝箱、怪物、gap 当成可走格。

## 6. 第一阶段完成标准

- [x] `planner.py` 能稳定返回安全路径，并能把 tile 路径转换成原子动作序列。
- [x] `controllers/task3.py` 不再是占位，能按阶段完成 Task 3。
- [x] 在像素输入加符号抽象的条件下，Task 3 至少通过单 seed smoke test。
- [x] 代码没有依赖最终推理禁用的隐藏结构化信息。
- [x] 对 B/C 视觉字段缺失或短暂误检有合理兜底，不会直接崩溃。

## 7. Task 3 泛化改造计划（第二轮）

### 7.1 新 pull 后接口变化

- [x] 已查看最新提交 `a4fe725 vision硬编码优化`：
  - `state.SymbolicState` 新增 `opened_chests`。
  - `planner.is_safe_tile()` 现在把 `opened_chests` 也视为阻塞。
  - `controllers/task2.py` 新增“玩家站在边界出口 tile 上时，根据边界方向执行跨房间动作”的四方向逻辑。
  - 视觉侧新增 `utils/evaluate_vision.py`，但 policy 仍只能使用 `SymbolicState`，不能读取隐藏 runtime truth。

### 7.2 当前 Task 3 主要问题

- [x] 出口只支持 `west/east`，不能表达 `north/south`。
- [x] 没钥匙默认向西、拿钥匙默认向东，本质上仍绑定公开地图拓扑。
- [x] `WEST_EXIT_TILES` / `EAST_EXIT_TILES` 在 controller 内硬编码边界坐标。
- [x] 没有维护当前房间 fingerprint、访问记录、出口尝试记录或房间图。
- [x] BFS 到出口失败时直接按方向键，可能在变体地图中盲走。

### 7.3 改造目标

- [x] 从当前视觉状态中动态识别四方向出口：
  - `x == 0` -> `west`
  - `x == MAP_WIDTH_TILES - 1` -> `east`
  - `y == 0` -> `north`
  - `y == MAP_HEIGHT_TILES - 1` -> `south`
- [x] 为当前房间构造静态 fingerprint，避免依赖隐藏 room id。
- [x] 使用 `memory.visited_rooms` / `memory.current_room_key` / `memory.notes` 维护：
  - 已访问房间
  - 已尝试出口
  - 跨房间前的 pending exit
  - 观察到的 room graph
  - 可能的最终锁门/目标出口
- [x] 保留 Task2 式状态驱动优先级：
  - 先处理怪物
  - 再处理宝箱
  - 有钥匙后优先走已知目标出口或回溯路径
  - 没有当前目标时探索未尝试出口
- [x] 避免新增持久测试文件；如需构造泛化场景，用临时/内联符号态测试，测试后不留下额外测试代码。

### 7.4 验证与评估口径

- [x] `python -m py_compile controllers/task3.py planner.py state.py`
- [x] 内联构造至少三类符号态场景：
  - 原公开 Task3 的 west/east 链式地图流程。
  - key room / 目标出口出现在 `north/south` 的变体。
  - 当前房间有多个出口时优先选择未探索出口，并记录 pending exit。
- [x] 完成后评估：
  - 是否仍存在坐标级硬编码。
  - 是否仍存在任务路线级硬编码。
  - 是否只依赖允许使用的 `SymbolicState` / `AgentMemory`。
  - 房间 fingerprint 和 room graph 对同类型变体地图的泛化边界。

### 7.5 完成记录

- [x] `controllers/task3.py` 已移除 `WEST_EXIT_TILES` / `EAST_EXIT_TILES`。
- [x] `controllers/task3.py` 已移除 `go_west_to_key_room` / `return_east_to_start_or_exit` 这类路线阶段。
- [x] 出口目标现在来自当前 `state.exits` 的边界分类，并缓存到 `memory.notes["task3_room_exit_tiles"]`；当前帧被玩家遮挡或视觉短暂漏检时，不会立刻遗忘之前见过的出口。
- [x] 跨出口前写入 `task3_pending_exit`；下一帧根据玩家是否离开原出口 tile 判断转场是否成功。
- [x] 转场成功时更新 `task3_room_graph`，同时记录反向边；转场失败时记录 `task3_blocked_exits`，无钥匙失败的出口额外记录为 `task3_key_gated_exits`，拿到钥匙后可优先重试。
- [x] 房间 identity 不直接等同于 fingerprint；如果两个房间静态视觉相同，仍通过 pending exit 产生的 room graph 节点区分。
- [x] 没有新增持久测试文件；泛化场景使用内联 Python 脚本验证。

### 7.6 验证结果

- [x] 静态编译：
  - `python -m py_compile controllers/task3.py planner.py state.py`
  - `python -m py_compile controllers/task3.py planner.py state.py agent.py vision.py`
- [x] 内联符号态测试：
  - 四方向出口选择通过。
  - 无钥匙撞到边界出口后，会记录 key-gated exit。
  - 拿到钥匙后，即使当前帧看不到被玩家遮挡的出口，也会使用记忆出口重试。
  - 跨房间成功后，会建立正向和反向 room graph 边。
- [x] Task 3 单环境评估：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 1`
  - seed 0 成功，667 steps，reward 163.330，`monster_killed=1.000`，`key_collected=1.000`。
- [x] Task 3 多 seed smoke：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_3 --num-envs 3`
  - seed 0/1/2 全部成功，平均 667 steps。
- [x] Task 2 回归：
  - `python utils/evaluate_policy.py --policy agent.py --tasks mathematical_logic/task_2 --num-envs 1`
  - seed 0 成功，332 steps，reward 161.680。

### 7.7 硬编码与泛化性评估

- [x] 坐标级硬编码：
  - 已删除 Task 3 专属的 `(0, 3)` / `(0, 4)` / `(MAP_WIDTH_TILES - 1, 3)` / `(MAP_WIDTH_TILES - 1, 4)` 出口常量。
  - 仍保留“边界即出口方向”的通用规则：`x == 0`、`x == MAP_WIDTH_TILES - 1`、`y == 0`、`y == MAP_HEIGHT_TILES - 1`。这是房间网格模型约定，不是 Task3 特定路线。
- [x] 路线级硬编码：
  - 已删除“无钥匙向 west、拿钥匙向 east”的任务路线。
  - 现在按未尝试出口、room graph、key-gated exit 选择方向。
- [x] 信息来源：
  - 未读取隐藏 `info["env"]`、`info["agent"]`、`room_id` 或实体真值。
  - 只依赖 `SymbolicState` / `AgentMemory`。
- [x] 泛化能力：
  - 支持 north/south/west/east 四方向出口。
  - 支持同一房间内多出口探索、失败出口记录、拿钥匙后重试 key-gated 出口。
  - 支持视觉短暂漏检或玩家遮挡出口时使用已观察过的出口 tile。
- [x] 泛化边界：
  - 如果视觉从未识别到某个出口，controller 不会凭空生成该出口坐标。
  - 如果两个视觉完全相同的房间没有通过 pending exit 建图连接，fingerprint 本身不能唯一判定它们是同一房间还是不同房间。
  - 如果出口失败原因不是缺钥匙，而是按钮、道具或其他条件，当前只会把“无钥匙时失败”的出口视作 key-gated；更复杂条件需要额外符号字段支持。
