# What D Have Done

## 1. 当前负责范围与正式提交位置

D 负责符号规划器和 Task 3 controller，并负责这一层的 Lean 形式化：

- `submissions/planner.py`：tile 级安全判断、BFS、目标邻接格、tile 路径转原子动作、房间图 BFS。
- `submissions/controllers/task3.py`：怪物、宝箱、钥匙、房间探索和条件出口重试。
- `submissions/lean/Environment.lean`：与 planner 对齐的符号状态和安全谓词。
- `submissions/lean/Strategy.lean`：planner 的可验证契约。
- `submissions/lean/TaskProofs.lean`：Task 3 阶段不变量和完成链。

### D 工作完成结论

按现有分工，D 的交付已经完成：

- 第一阶段的 planner、安全格、目标邻接格、tile 到原子动作转换和 Task 3 controller 已完成；
- 第二轮的四方向出口、room graph、key-gated 出口重试和跨出口像素偏移兼容已完成；
- 正式 `safe` 入口、Task 3 多 seed、Task 2 回归、Task 3 spatial 变体和可复现证据均已验证；
- 第二阶段中属于 D planner / Task 3 的 Lean 模型、动作编码和策略阶段证明已通过 `lake build`。

这项结论不等于整个项目已经完成：颜色变体下的对象识别仍是 B/C 视觉层的待改进项；Task 4/5
和其对应的 Lean 工作属于 E 或全组后续范围；`BFSReturns` 目前验证的是 planner 返回路径的契约，
不包含对 Python BFS 最短性或完备性的逐实现证明。

仓库合并后，正式 Python 入口为 `submissions.student_policy:make_policy`。旧的根目录
`planner.py`、`controllers/task3.py` 和 `agent.py` 已不再是提交入口。

正式 `safe` 评测应使用 task-specific 绑定：

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_3 \
  --task-policy mathematical_logic/task_3=submissions.student_policy:make_policy \
  --info-mode safe
```

共享 `--policy` 在 `safe` 模式下不会收到任务编号，不适用于当前按任务分派 controller
的提交结构。

## 2. Planner 实现

`submissions/planner.py` 当前提供：

- `in_bounds(pos)`：使用环境的 `MAP_WIDTH_TILES`、`MAP_HEIGHT_TILES`。
- `neighbors(pos)`：枚举上、下、左、右四邻接格。
- `is_safe_tile(state, pos)`：排除越界、墙、怪物、未开/已开宝箱、NPC、陷阱和 gap；
  bridge 覆盖 trap/gap 时允许通行。
- `action_from_step(current, nxt)`：将相邻 tile 边映射为方向动作，非相邻输入抛出
  `ValueError`。
- `bfs_path(state, goals)`：返回到目标集合的最短 tile 路径。
- `adjacent_goal_tiles()` / `bfs_path_to_adjacent_target()`：为怪物、宝箱等不可直接
  踩入的交互对象规划安全邻接格。
- `actions_for_tile_path(path)`：每条 tile 边展开为 `TILE_SIZE = 16` 个原子方向动作。
- `bfs_graph_path()`：在已发现的房间图上搜索目标房间。

Planner 只依赖像素视觉产生的 `SymbolicState`，不读取 room id、实体真值或环境内部对象。

## 3. Task 3 泛化 controller

### 3.1 局部优先级

每个房间都使用同一套状态驱动优先级：

1. 视觉未识别玩家时等待。
2. 当前房间存在怪物时，规划到安全邻接格，面向怪物并攻击。
3. 没有钥匙且存在未开启宝箱时，规划到邻接格并交互。
4. 宝箱已经打开但 inventory 尚未更新时等待一帧。
5. 其余情况根据房间图、未探索出口和 key-gated 出口导航。

当前实现不再包含“无钥匙固定向西、拿到钥匙固定向东”的路线阶段。

### 3.2 四方向出口与房间图

controller 从视觉中的边界出口动态识别方向：

- `x == 0`：west
- `x == MAP_WIDTH_TILES - 1`：east
- `y == 0`：north
- `y == MAP_HEIGHT_TILES - 1`：south

跨房间前记录 `task3_pending_exit`。成功转场后建立正向和反向 room graph 边；失败出口
进入 blocked 集合，无钥匙时失败的出口额外记为 key-gated，拿到钥匙后优先重试。
已观察到的出口 tile 会缓存在 memory 中，以处理玩家遮挡出口或视觉短暂漏检。

### 3.3 spatial 回归中修复的跨出口问题

符号状态只有 tile 坐标，不包含玩家在 tile 内的精确像素偏移。旧实现站到出口 tile 后只按
一次方向键，并在下一帧仍位于出口 tile 时直接判定门被阻挡。改变出生点或对象位置后，
这会误判普通出口。

当前实现会在 pending exit 状态下持续按跨越方向，最多尝试一个 tile 宽度
`TILE_SIZE`，仍未转场才判定出口阻塞。该修复使 `spatial_a/b/c` 从 0/3 提升到 3/3。

### 3.4 正式评测入口修复

最新评测器在 episode 开始时无参数调用 `policy.reset()`，task-specific 的任务编号在首帧
`safe_info["task_id"]` 中提供。`submissions/student_policy.py` 现会在首次 `act()` 时根据该
公开字段选择 controller，因此 Task 3 不再错误落入 `BaseController`。

## 4. 信息边界

最终推理只使用：

- raw RGB `obs`
- `safe_info["inventory"]`
- task-specific 绑定公开提供的 `safe_info["task_id"]`
- `SymbolicState` 和 `AgentMemory`

没有读取：

- `info["env"]` 或 room id
- `info["agent"]` 中的坐标、血量和朝向
- `info["entities"]` / `info["dynamic"]` 的运行时真值
- reward 事件或完成状态来替代策略判断

评测器内部使用完整 info 统计结果，但不会把这些字段传给 policy。

## 5. Python 验证结果

结果 JSON 保存在 `results/d/`。

### 5.1 Task 3 多 seed

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_3 \
  --task-policy mathematical_logic/task_3=submissions.student_policy:make_policy \
  --num-envs 10 \
  --info-mode safe \
  --json-out results/d/task3_multiseed_final.json
```

结果：10/10 成功，平均 962 steps，平均 reward 177.530；全部 `world_completed`，且
全部达到 `monster_killed` 和 `key_collected`。

### 5.2 Task 2 planner 回归

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_2 \
  --task-policy mathematical_logic/task_2=submissions.student_policy:make_policy \
  --num-envs 5 \
  --info-mode safe \
  --json-out results/d/task2_regression.json
```

结果：5/5 成功，平均 332 steps，平均 reward 161.680。

### 5.3 Task 3 spatial 鲁棒性

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_3 \
  --task-policy mathematical_logic/task_3=submissions.student_policy:make_policy \
  --num-envs 10 \
  --info-mode safe \
  --robustness-suite \
  --json-out results/d/task3_robustness_after_fix.json
```

结果：

| 阶段 | 成功率 | 平均 steps | 说明 |
|---|---:|---:|---|
| original | 6/6 | 962.0 | 全部完成 |
| spatial | 3/3 | 872.7 | `spatial_a/b/c` 各一次，全部完成 |
| color | 0/1 | 1500.0 | grayscale 下视觉模型未识别关键对象 |

颜色变体失败位于 B/C 视觉模型的颜色鲁棒性边界，不是 D 的符号规划失败；报告中应如实注明。

## 6. 可复现截图证据

新增 `utils/capture_policy_evidence.py`，使用与正式评测相同的 `safe_info`，在首次出现关键
事件时保存完整渲染帧和 manifest。

```bash
python utils/capture_policy_evidence.py \
  --policy submissions.student_policy:make_policy \
  --task mathematical_logic/task_3 \
  --seed 1 \
  --map-variant spatial_b \
  --output-dir results/d/task3_spatial_b_evidence
```

该轨迹结果：成功，988 steps，reward 177.270。保存了：

- 起始画面
- `monster_killed`（step 144）
- `key_collected` / `chest_opened`（step 672）
- `door_opened` / `world_completed`（step 988）

具体文件和参数见 `results/d/task3_spatial_b_evidence/manifest.json`。

## 7. Lean 形式化与证明

工具链由 `lean-toolchain` 固定为 `leanprover/lean4:v4.29.0-rc6`。

### 7.1 环境与安全谓词

`Environment.lean` 中的 `isSafe` 与 Python planner 对齐：

- 坐标在 `10 × 8` 边界内；
- 不进入墙、怪物、未开/已开宝箱或 NPC；
- trap/gap 仅在没有 bridge 覆盖时阻塞。

`safe_move_preserves_safe_state` 证明合法安全移动后的玩家仍处于安全状态。

### 7.2 Planner 契约

`Strategy.lean` 定义并证明：

- `PlannerSound` / `BFSReturns`：返回路径从玩家开始、在目标结束、所有 tile 安全且逐步相邻；
- `bfs_return_starts_at_player`；
- `bfs_return_ends_in_goal`；
- `bfs_return_path_safe`；
- `bfs_return_path_adjacent`；
- `adjacent_goal_sound`；
- `encoded_tile_step_is_move`；
- `encoded_tile_step_adjacent`；
- `actions_for_path_are_moves`；
- `actions_follow_adjacent_path`；
- `actions_for_single_tile_empty`；
- `actions_for_one_step_repeat`：单条 tile 边对应 `tileSize = 16` 个相同方向动作。

Lean 证明的是 Python BFS 返回值必须满足的可验证契约；搜索完备性和神经网络分类正确性
没有被伪装成 `axiom`。

### 7.3 Task 3 阶段不变量

`TaskProofs.lean` 新增：

- `task3_monster_priority`
- `task3_chest_after_monsters`
- `task3_waits_for_inventory_update`
- `task3_navigates_after_key`
- `task3_cross_exit_budget_positive`
- `task3_monster_then_chest_then_exit_chain`

最后一个定理证明：在攻击、开箱和到达出口这些动作前提成立时，执行
“清除怪物 → 获取钥匙 → 到达出口”后满足 Task 3 完成谓词。

### 7.4 编译验证

```bash
lake build
lake env lean submissions/lean/TaskProofs.lean
```

两条命令均通过。提交 Lean 文件没有 `sorry`、`admit` 或 `axiom` 声明。

## 8. 已知边界与后续建议

- grayscale、反色等颜色偏移会使当前视觉模型失效，需要 B/C 扩充增强训练或规则归一化。
- 房间图只基于已观察出口建立；从未被视觉识别的出口无法由 planner 凭空发现。
- `BFSReturns` 当前是执行器输出契约，不是 Lean 内重新实现的可计算 BFS。若报告要求证明搜索
  完备性，可后续在有限 `Fin 10 × Fin 8` 网格上实现纯 Lean BFS 并证明终止与完备性。
- 最终报告应同时列出通过的 original/spatial 结果和未通过的 color 结果，明确证明边界与视觉
  假设。
