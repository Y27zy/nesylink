# NesyLink 数理逻辑课程设计报告

本报告按评分细则的三个核心模块组织：环境形式化、策略形式化与证明、策略性能；最后说明本项目实际满足的加分项。报告中的形式化结论均对应提交的 Lean 源码，性能结论均来自随报告提交的正式测评 JSON。

## 1. 环境形式化

### 1.1 状态、动作、对象与目标是否定义齐全

环境模型位于 [`Environment.lean`](../lean/Environment.lean)。它把 Python 环境抽象为一个 10×8 的 tile 世界，并给出以下核心定义：

| 评分点 | Lean 定义 | 覆盖内容 |
| --- | --- | --- |
| 状态 | `State` | 当前房间、玩家位置与朝向、生命值、钥匙/金币/剑/盾、墙与危险地形、宝箱、出口、怪物、按钮、开关、桥状态、已访问房间和任务进度 |
| 动作 | `Action` | `up/down/left/right`、`attack`、`shield`、`wait` |
| 对象及属性 | `Chest`、`Monster`、`Exit` | 宝箱种类及是否完成世界；怪物种类、位置和 HP；出口方向、目标房间、到达位置、门类型及是否完成世界 |
| 空间与安全谓词 | `inBounds`、`walkable`、`isSafe` | 边界、碰撞以及陷阱/gap/活动桥共同决定的安全性 |
| 单步与轨迹 | `Step`、`Exec` | 一步环境转移及多步轨迹 |
| 关卡目标 | `TaskGoal`、`TaskCompletable` | 五关完成条件及“存在合法计划达到目标”的可完成性 |

`walkable` 与 `isSafe` 被有意区分：前者表示引擎允许进入，后者还排除未被活动桥覆盖的陷阱和 gap。因此模型没有把“危险”错误地等同于“不可移动”，策略仍可证明自己只选择更强的安全移动。

五个 `TaskGoal` 直接刻画评分所需的最终状态：Task 1 要求完成世界且取过钥匙；Task 2 进一步要求击杀怪物；Task 3 还要求访问至少两个房间；Task 4 要求取得钥匙和剑、击杀怪物并获得金币；Task 5 要求世界完成、所有世界宝箱均已打开，并完成钥匙、金币和按钮里程碑。

### 1.2 动作转移是否合理，是否覆盖关键机制

`Step s a t` 是关系式转移语义，既保留环境可能发生的危险行为，也允许策略只选择其中安全的构造。其覆盖范围如下：

| 机制 | 转移构造及效果 |
| --- | --- |
| 移动与碰撞 | `moveSafe` 更新位置和朝向；`moveDanger` 进入危险格并扣血；`moveBlocked` 保持位置、只更新朝向 |
| 怪物与战斗 | `monsterDamage` 表示邻近怪物伤害；`attackDamage` 降低怪物 HP；`attackKill` 移除怪物并增加击杀计数 |
| 宝箱 | `openChest` 根据 `ChestKind` 发放钥匙、金币、治疗、剑、盾或物品，并更新开箱和世界完成进度 |
| 按钮与开关 | `pressButton` 记录按钮事件；`activateSwitch` 切换水平/垂直桥状态 |
| 门与换房 | `crossExit` 检查普通门、钥匙门或条件门；钥匙门消耗一把钥匙，并更新房间、到达点、已访问房间和世界完成状态 |
| 无效果动作 | `attackNoEffect`、`wait`、`shield` 明确给出非移动动作的语义 |

`Exec` 递归连接多步 `Step`；`exec_append` 证明两段合法轨迹可以拼接。这一结果是后续把“到达目标附近的规划路径”和“开箱、攻击、过门等交互”组合为整关轨迹的基础。

### 1.3 是否证明基本安全性或不变量

环境层不只定义语义，还证明了以下代表性性质；完整定理位于 [`TaskProofs.lean`](../lean/TaskProofs.lean)。

| 性质 | 代表性定理 | 实际保证 |
| --- | --- | --- |
| 合法移动 | `safe_implies_walkable`、`selected_safe_move_is_environment_step` | 安全格一定可通行，策略选择的安全移动确实对应环境的一步转移；由于 `isSafe` 含 `inBounds` 且排除墙体，因此该结论同时覆盖不越界、不进墙 |
| 危险与桥 | `uncovered_gap_is_not_safe`、`active_bridge_covers_hazards` | 未覆盖 gap 不安全；活动桥能覆盖同格陷阱/gap |
| 门与机关 | `locked_exit_requires_key`、`conditional_exit_requires_trigger`、`locked_exit_consumes_one_key`、`selected_switch_changes_bridge_mode` | 锁门、条件门、钥匙消耗和旋桥效果符合关卡规则 |
| 宝箱与完成 | `key_chest_effect`、`gold_chest_effect`、`sword_chest_effect`、`opening_last_chest_finishes_world` | 关键宝箱的资源效果正确，最后一个世界宝箱会完成世界 |
| 进度不回退 | `step_*_mono`、`exec_*_mono` | 已开宝箱数、击杀数、按钮数、金币、钥匙里程碑和持剑状态在一步及整段轨迹上保持单调 |

### 1.4 环境抽象与简化

Lean 模型验证的是策略使用的符号层，而不是逐像素复制整个游戏引擎。主要边界如下：

- 连续像素运动被抽象为相邻 tile 转移；Python 中的子 tile 对齐、碰撞恢复和动画时序不在 Lean 中展开。
- 怪物移动轨迹和精确碰撞几何被抽象为当前位置、类型、HP 与邻近威胁；总任务定理从“最后一击已经可执行”的状态组合战斗结果。
- 按钮、开关和门的地图脚本被抽象为按钮记录、桥模式切换和出口启用条件，不声称覆盖未被五关使用的任意脚本效果。
- Lean 状态来自视觉构造的符号状态；神经网络对任意 RGB 图像都正确并未被假设成无条件定理，而是在策略层通过显式感知契约处理。

## 2. 策略形式化与证明

### 2.1 策略如何工作，机器学习输出如何进入可验证层

共享入口为 [`student_policy.py`](../student_policy.py)。正式推理的数据流是：

```text
RGB obs + last_reward + inventory
        → 静态 tile CNN + 动态 CenterNet
        → SymbolicState + 跨帧/跨房间 AgentMemory
        → 单房间 BFS + 房间图搜索 + 任务阶段优先级
        → tile 路径编码为像素动作
```

静态网络识别地形、对象、宝箱类型、出口类型和对象状态；动态网络输出玩家及三类怪物的中心热图、亚网格偏移和玩家朝向。两者的权重分别为 [`static_tile_multitask.pt`](../models/static_tile_multitask.pt) 和 [`dynamic_centernet.pt`](../models/dynamic_centernet.pt)。

训练样本由 [`generate_dataset.py`](../training/generate_dataset.py) 调用游戏同源 renderer 自动合成并直接产生监督标签，随机化地形、交互状态、遮挡、连续像素位置、怪物数量以及五种正式颜色变体。训练不把环境 `info` 作为模型输入：

| 模型 | 输入与输出 | 训练方式 | 权重元数据 |
| --- | --- | --- | --- |
| 静态多头 CNN | 9 通道的 16×16 tile；输出 terrain/object/chest/exit/state 五个 head | AdamW；分类交叉熵，state head 权重 0.7 | seed `2026071801`，400 steps |
| 动态 CenterNet | 9 通道的 128×160 全帧；输出四类中心热图、offset 和玩家朝向 | AdamW；CenterNet focal loss + 2.0×Smooth-L1 + 0.35×朝向交叉熵 | seed `20260718`，350 steps |

Lean 不证明这两个网络对所有输入永远正确，而是在 [`Strategy.lean`](../lean/Strategy.lean) 中以 `PerceptionContract observed actual` 明确网络输出与真实符号状态之间的关系：玩家位置一致；真实墙、陷阱、gap、NPC、宝箱和怪物不能被安全层漏报；被观测为活动桥的格子必须真实活动。契约允许保守地多报障碍，因为这可能降低可达性，但不会把危险格误判成安全格。

### 2.2 策略输出是否合法、安全并满足目标

可验证层按“感知契约—动作约束—搜索—任务组合”分层：

| 证明义务 | 形式化对象与主要定理 | 结论 |
| --- | --- | --- |
| 动作合法性 | `ActionAllowed`、`maskedAction`、`masked_action_allowed` | 不合法的候选动作被替换为 `wait`，mask 的输出总满足动作规范 |
| 感知后的真实安全性 | `perceived_safe_is_actually_safe`、`masked_move_is_safe_for_actual_state` | 在 `PerceptionContract` 成立时，观测中判为安全的移动目标在真实状态中也安全 |
| 路径正确性 | `BFSReturns`、`PathStartsAt`、`PathEndsIn`、`PathSafe`、`PathAdjacent` | 返回路径从玩家出发、在目标处结束、每格安全且相邻 |
| 路径到动作 | `EncodesTileStep`、`ActionsFollowPath`、`actions_follow_adjacent_path` | 相邻 tile 路径只能编码为对应的四向移动动作 |
| 轨迹安全 | `planner_step_safe`、`run_moves_safe`、`verified_move_preserves_safe_state` | 从安全起点执行 planner 移动保持安全状态 |
| 房间记忆 | `MemoryConsistent`、`record_transition_preserves_consistency` | 记录换房后，当前房间、已访问集合和已知房间边仍保持一致 |
| 整关目标 | `task1_strategy_completes` 至 `task5_strategy_completes` | 在各规划子路径均满足 `Exec`、交互前提成立时，可拼接出满足相应 `TaskGoal` 的完整轨迹 |

Python 的 [`planner.py`](../planner.py) 对四邻接安全格执行 BFS，并用 parent map 重建路径；宝箱、怪物和开关被转换为“到达其安全邻接格后面向交互”。Task 3–5 还在线建立房间图，区分已探索、未探索、暂时受阻和钥匙门边，并以房间级 BFS 找到最近 frontier 或待重试目标。五个 controller 复用同一视觉、符号状态和基础 planner，主体差异集中在高层优先级及多房间恢复逻辑：Task 1 取钥匙后开门；Task 2 先战斗再取钥匙；Task 3 在此基础上探索并回溯钥匙门；Task 4 分阶段完成钥匙、剑、怪物和胜利宝箱，并在需要时检查或切换桥；Task 5 优先安全举盾、关键宝箱、按钮和剩余房间探索。

### 2.3 是否证明搜索完备性，证明边界是什么

`bfsVisited` 和 `bfsRooms` 是可计算的 Lean 定义。`bfs_complete_for_bounded_goal` 证明：若在给定 `depth` 内存在一条由四向移动组成的可行路径，则目标必出现在 BFS 的 visited 中。`room_bfs_complete` 将同一结论推广到房间图；`task345_room_search_complete` 把它连接到多房间策略。因此本项目证明的是评分细则所鼓励的“存在有界可行路径则搜索不会漏掉”，而不是对无限地图作无界完备性声明。

还需明确三点限制：第一，没有证明 Python 实现逐行等价于 Lean 定义；第二，像素动作序列到 tile edge 的成功对齐仍由 Python 执行层负责；第三，五个整关定理是条件式组合定理，其前提明确要求感知契约、合法子路径和相应交互条件成立。正式实验用于检验这些前提在公开鲁棒性套件中是否能端到端满足，不能替代未证明的网络全输入正确性。

三个 Lean 文件按职责分为环境语义、策略/搜索和任务定理，命名直接反映性质。2026-07-19 重新执行 `lake build`，结果为 `Build completed successfully (5 jobs)`；源码中不存在 `sorry`、`admit` 或自定义 `axiom`。

## 3. 策略性能

### 3.1 黑盒接口是否合规、实验能否复现

正式测评使用共享 `--policy`，因此 safe 模式不会向策略提供 `task_id`。策略只读取 `(128, 160, 3)` RGB `obs`、`last_reward` 和公开 `inventory`；任务类型由首个房间的视觉符号和允许使用的物品栏推断。`student_policy.py` 不读取玩家坐标、房间 ID、对象坐标、地图真值、事件、终止原因或其他隐藏 `info` 字段。测评器读取完整环境状态仅用于统计成功、事件和 milestone，不进入 Agent 决策。

实际命令为：

```powershell
python utils/evaluate_policy.py `
  --policy submissions/student_policy.py `
  --info-mode safe `
  --robustness-suite `
  --num-envs 100 `
  --seed 0 `
  --json-out results/robustness_suite_eval_final.json
```

每个任务运行 100 个 episode：`original` 60 个，`spatial_a/b/c` 共 30 个，五种 `color` 变体共 10 个；未覆盖任务默认的 `max_steps` 和 `action_repeat`。测评期间只进行 CPU 推理，不更新模型权重。结果对应代码提交 `f567418901ce3b6da16c6171cea3c891333bcdae`。

| 随提交提供的权重/结果 | SHA-256 |
| --- | --- |
| `models/static_tile_multitask.pt` | `5F6A4995EEC825D2BD810050656D7FFE7DB41B8258A288CBF78259D54EF5FFF9` |
| `models/dynamic_centernet.pt` | `9A67BCD1D57473EF34859D61303B4B8A399632240B2E7A0C72B588A24B3B7A46` |
| `report/robustness_suite_eval_final.json` | `12C073E626AF77A56A88B0DD97249596503BB849DCFED613BE18F6CDD017B460` |

### 3.2 多次运行的成功率和完成程度

以下数值直接取自 [`robustness_suite_eval_final.json`](./robustness_suite_eval_final.json)：

| Task | 阶段 | Episodes | 成功率 | avg_steps | avg_reward |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | original | 60 | 100% | 290.00 | 127.050 |
| 1 | spatial | 30 | 100% | 178.00 | 128.170 |
| 1 | color | 10 | 100% | 290.00 | 127.050 |
| 2 | original | 60 | 100% | 189.00 | 151.110 |
| 2 | spatial | 30 | 100% | 196.67 | 148.017 |
| 2 | color | 10 | 100% | 189.00 | 151.110 |
| 3 | original | 60 | 100% | 1216.00 | 197.190 |
| 3 | spatial | 30 | 100% | 1229.33 | 199.040 |
| 3 | color | 10 | 100% | 1227.00 | 197.080 |
| 4 | original | 60 | 100% | 1143.00 | 256.570 |
| 4 | spatial | 30 | 100% | 1444.00 | 270.493 |
| 4 | color | 10 | 100% | 1151.20 | 256.578 |
| 5 | original | 60 | 100% | 1085.00 | 156.050 |
| 5 | spatial | 30 | 100% | 1127.00 | 150.247 |
| 5 | color | 10 | 100% | 1126.40 | 152.236 |

总计 **500/500 成功，成功率 100%**；15 个“任务×阶段”分组的 `environment_completed` 和 `world_completed` 也全部为 100%。阶段性指标可压缩为下表，而无需重复整份 JSON：

| Task | milestone / progress 结果 |
| --- | --- |
| 1 | 三阶段的开箱、取钥匙、开门、换房、到达出口及环境/世界完成均为 100% |
| 2 | 三阶段的开箱、取钥匙、击杀怪物、到达出口、换房及环境/世界完成均为 100% |
| 3 | 三阶段的 `key_collected`、`monster_killed` milestone 均为 100%；全部 progress 指标也均为 100% |
| 4 | 三阶段的开关、钥匙、开门、物品和击杀 milestone 均为 100%；开箱、金币、出口、换房及环境/世界完成 progress 也均为 100% |
| 5 | 三阶段的治疗、按钮、开箱、开门、金币、钥匙、出口、换房及环境/世界完成均为 100%；`monster_killed` 为 original 100%、spatial 33.33%、color 60%；`item_collected` 和 `trap_triggered` 均为 0% |

Task 5 的目标是打开所有世界宝箱，不要求清空怪物，因此空间/颜色阶段较低的击杀率不影响成功判定；其公开宝箱没有装备型 `item`，所以 `item_collected=0%` 不是漏做子任务；`trap_triggered=0%` 则是期望的安全结果。500 个 episode 中没有 `agent_dead` 事件。

空间变体改变布局、出生点或对象位置，颜色变体依次使用 grayscale、dark、bright、high_contrast 和 inverted。所有空间与颜色分组均为 100%，表明策略不是固定坐标或固定动作回放。代价是多房间任务步数较高，尤其 Task 4 spatial 的平均 1444 步；这是在线建图、frontier 探索和受阻门重试带来的效率成本，但仍低于该任务默认 2000 步上限并全部通关。

## 4. 实际满足的加分项

1. **机器学习与自动化感知。** 两个监督学习视觉模型直接从 RGB 构造符号状态；样本和标签由 renderer 自动生成，并通过颜色增强、遮挡和连续像素位置随机化提高自动化程度，不依赖手工逐帧标注。
2. **统一策略、结构复用与泛化。** 五关使用同一个 `student_policy.py` 和同一组视觉权重，共享 `SymbolicState`、BFS、房间记忆和交互执行层；只有可解释的高层任务优先级不同。共享策略在不接收 `task_id` 的 safe 测评中完成 500/500，并在三类空间布局和五类颜色变化下保持 100%。
3. **超出基础要求的定理。** 除移动不越界、不进墙及关键机制效果外，还证明了感知契约下的真实安全性传递、action mask 合法性、路径编码正确性、tile 与房间两层 BFS 的有界完备性、房间记忆一致性、关键进度单调性，以及五关目标轨迹的条件式组合正确性。
