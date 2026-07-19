# NesyLink Task 1-5 Lean Formalization

本目录是最终 Python agent 的形式化层，对应课程评分中的“环境形式化”与“策略形式化与证明”。所有定理均由 Lean 4 检查，不包含 `sorry`、`admit` 或自定义 `axiom`。

## 文件关系

- `NesyLinkAll.lean` 是唯一的 Lean 源文件，不依赖本目录中的其他 Lean 模块。
- 文件内部依次组织环境语义、可验证策略层和任务级证明，保留原有的职责边界与命名结构。

Python 对应关系：

| Lean | Python |
|---|---|
| `State` | `state.py::SymbolicState` 与允许使用的 inventory |
| `PerceptionContract` | `vision.py` 的静态/动态融合与房间 belief |
| `isSafe` / `ActionAllowed` | `planner.py::is_safe_tile` 与 controller 安全约束 |
| `bfsVisited` | `planner.py::bfs_path` 的有界可达性核心 |
| `RoomMemory` / `bfsRooms` | `AgentMemory`、Task 3 room graph、Task 4/5 `RoomExplorer` |
| `ActionsFollowPath` | `planner.py::actions_for_tile_path` |
| `task1Phase` ... `task5Phase` | 五个 controller 的稳定高层优先级 |

## 环境形式化覆盖

`NesyLinkAll.lean` 的环境语义部分对以下内容进行了显式建模：

1. `10 x 8` tile 房间、`16` 像素 tile、位置、房间编号、朝向和七个离散动作。
2. 类型化宝箱：key、gold、heal、sword、shield、item，并记录胜利宝箱属性；最后一个世界宝箱被打开时更新完成状态。
3. 类型化出口：normal、locked-key、conditional，并记录目标房间、到达位置和是否完成世界。
4. 三类怪物、HP、玩家 HP、钥匙、金币、剑盾装备和任务事件计数。
5. 墙、NPC、陷阱、gap、水平/垂直桥、按钮、switch、已访问房间和剩余世界宝箱。
6. `walkable` 与 `isSafe` 的区别：陷阱和未覆盖 gap 可由环境进入但不被安全 planner 选择。
7. `Step` 转移：安全移动、危险移动、碰撞、怪物伤害、攻击伤害、击杀、开箱、按钮、switch 旋桥、无效交互、盾牌、等待和跨房间出口。
8. `Exec` 多步执行关系与 `exec_append` 轨迹组合定理。
9. `TaskGoal` 对 Task 1-5 的完成事件、资源和关键里程碑要求。

环境机制证明包括：

- `uncovered_gap_is_not_safe`
- `active_bridge_covers_hazards`
- `locked_exit_requires_key`
- `conditional_exit_requires_trigger`
- `locked_exit_consumes_one_key`
- `selected_switch_changes_bridge_mode`
- `key_chest_effect` / `gold_chest_effect` / `sword_chest_effect`
- `selected_button_press_records_event`
- `crossing_completing_exit_finishes_world`
- `opening_victory_chest_finishes_world` / `opening_last_chest_finishes_world`

## 策略形式化与证明

### 视觉到符号层

神经网络本身不在 Lean 中展开。`PerceptionContract observed actual` 明确规定可验证层所需的条件：真实墙、怪物、宝箱、NPC、trap 和 gap 不得被漏报；被视觉判定为活动桥的 tile 必须确实是活动桥。允许保守的额外障碍。

`perceived_safe_is_actually_safe` 证明：在该契约下，观测符号状态中判定安全的 tile 在真实符号状态中也安全。`masked_move_is_safe_for_actual_state` 将此结论连接到 action mask。

### Action mask 与路径执行

- `ActionAllowed` 只允许朝安全 tile 移动；attack 必须有可攻击怪物、可开宝箱或可操作 switch；shield 必须已持盾。
- `maskedAction` 将不合法候选动作替换为 `wait`。
- `masked_action_allowed` 证明 mask 输出总是合法。
- `verified_move_preserves_safe_state` 证明允许的移动保持玩家存活和 tile 安全。
- `EncodesTileStep` 与 `ActionsFollowPath` 证明相邻 tile 会被编码成正确方向的 16 次像素移动。

### BFS 与多房间记忆

`bfsVisited` 是对四方向安全后继进行逐层展开的 bounded BFS。它不去重，因而是适合证明的可达性核心；去重只影响 Python 实现效率，不影响下面的完备性结论。

- `run_moves_safe`：任意 planner 动作序列都保持在安全 tile。
- `run_moves_mem_bfs`：长度不超过 `n` 的移动计划，其终点一定出现在深度 `n` 的 BFS visited 集合中。
- `bfs_complete_for_bounded_goal`：若深度界内存在到目标的路径，BFS 必能发现某个目标。
- `room_bfs_complete`：同一结论推广到 agent 在线发现的多房间图。
- `record_transition_preserves_consistency`：记录换房后，当前房间、visited 集合和 room edge 仍一致。

## 五关证明

高层 phase 定理与最终 Python controller 的优先级一致：

- Task 1：无钥匙先找宝箱，有钥匙后找锁门。
- Task 2：怪物优先于钥匙宝箱，之后离开。
- Task 3：当前房间先处理怪物/钥匙，再通过房间图探索和重试出口。
- Task 4：宝箱优先；有剑才攻击；桥状态检查后操作 switch；否则继续房间图探索。
- Task 5：危险窗口先举盾；key chest 优先；可选宝箱、按钮、frontier 和 retry 按条件选择。

五个主定理：

- `task1_strategy_completes`
- `task2_strategy_completes`
- `task3_strategy_completes`
- `task4_strategy_completes`
- `task5_strategy_completes`

这些定理不是把最终状态作为等式前提。它们使用真实 `Step` constructor 构造开箱、击杀、按钮、旋桥和出口转移，并用 `Exec` 拼接 BFS 子路径。Task 4 的总轨迹显式包含 switch 旋桥、钥匙宝箱、剑宝箱、guardian 击杀和胜利宝箱；Task 5 显式包含按钮、钥匙宝箱、其它房间子路径、最后金币宝箱和“所有宝箱已打开”的完成判定。

`step_*_mono` 与 `exec_*_mono` 系列定理证明钥匙收集数、开箱数、击杀数、按钮数和金币不会在合法执行中减少，获得剑后也不会丢失。因此每个局部里程碑可以可靠地组合成最终目标。

## 证明边界与简化

1. Lean 从视觉抽取后的 tile-level 符号状态开始，不证明 ResNet 对所有 RGB 输入都正确；视觉与真实状态的关系由公开的 `PerceptionContract` 表达。
2. 像素内对齐、碰撞恢复和怪物动画时序在 Python 中执行；Lean 将成功对齐后的 16 像素移动抽象为一条 tile edge。
3. 怪物多次受击由 `attackDamage` 和最终 `attackKill` 分开建模；任务总定理从最后一击可执行的状态开始组合。
4. 多房间地图不使用固定坐标。总定理只要求 planner 给出合法子路径，因此适用于评测中的位置和布局变体。
5. BFS 完备性是有界完备性：若路径长度不超过给定 depth，则目标必被发现。这与有限 `10 x 8` 房间和评测步数上限一致。

## 构建检查

在项目根目录运行：

```powershell
lake build
lake env lean submissions\lean\NesyLinkAll.lean
```

项目工具链由 `lean-toolchain` 固定为 `leanprover/lean4:v4.29.0-rc6`。
