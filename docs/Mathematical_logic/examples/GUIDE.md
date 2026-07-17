# `examples/` 阅读指南

这个目录不是一套可以直接提交的最终 Agent，而是四份从不同层次解释作业的教学材料：

| 文件 | 你会学到什么 | 是否可直接作为正式提交 |
|---|---|---|
| `agent.py` | 测评器要求的最小 `Policy` 接口 | 仅 Task 1 的固定地图/固定动作演示，不建议 |
| `task1_reference.py` | 如何直接创建环境、回放像素级动作、读取执行结果 | 仅本地教学与调试 |
| `task2_reference.py` | 如何从符号状态出发，用 BFS 规划“打怪 → 开箱 → 出口” | 仅本地教学与调试 |
| `KillMonsterFormalization.lean` | 如何把符号策略、状态转移、BFS 性质和具体关卡轨迹写成 Lean 定理 | 可以作为 Lean 写法参考，不是当前最终提交文件 |
| `txt` | 上述 Python 示例的简短目录说明和命令 | 目录索引 |

推荐阅读顺序是：`agent.py` → `task1_reference.py` → `task2_reference.py` →
`KillMonsterFormalization.lean`。先建立“动作怎样进入环境”的直觉，再看“如何规划”，最后看“如何证明”。

## 0. 先区分两种使用场景

`task1_reference.py` 和 `task2_reference.py` 为了教学便利，会直接读取完整的 `info`，例如：

- `info["agent"]["tile"]`、`info["agent"]["position_px"]`；
- `info["agent"]["hp"]`；
- `info["entities"]` 中的怪物和宝箱数量；
- 固定的怪物、宝箱、出口坐标。

这些信息可用于本地观察、构造参考符号状态和检查环境行为；但正式默认
`--info-mode safe` 不会提供它们。正式 Agent 只能使用像素 `obs`、公开 inventory，以及为
task-specific policy 提供的 `info["task_id"]`。因此应把这些文件理解为“概念和接口示例”，
不要直接复制其 `extract_symbolic_state()` 到最终提交。

本仓库当前的正式实现可对照：

- [提交入口](../../../submissions/student_policy.py)
- [像素到符号状态](../../../submissions/vision.py)
- [通用 planner](../../../submissions/planner.py)
- [Task 3 controller](../../../submissions/controllers/task3.py)

## 1. `agent.py`：最小 Policy 接口

这是最短、最值得先读的文件。它说明测评器会寻找：

1. `Policy` 类；
2. `reset()`：每个 episode 开始时重置内部索引；
3. `act(obs, info)`：每一步返回一个离散动作编号；
4. `make_policy()`：创建 policy 对象的推荐工厂函数。

代码流程：

```text
build_task1_plan() 生成整段动作列表
        ↓
Policy.reset() 把 index 置回 0
        ↓
Policy.act() 每次弹出一个动作；用尽后返回 ACTION_NOOP
```

`repeat(action, count)` 很关键：环境是像素控制，移动一个 tile 通常不是一个动作，而是连续
执行约 16 次同方向动作。`build_task1_plan()` 中的 `48`、`96` 就分别对应 3、6 个 tile 的移动。

这个文件故意 `del obs, info`，用来强调它是固定 replay：不看输入，因此只适用于它写死的
Task 1 地图和起点。它适合学习接口，不适合作为泛化策略模板。

可运行：

```bash
python utils/evaluate_policy.py \
  --policy docs/Mathematical_logic/examples/agent.py \
  --tasks mathematical_logic/task_1 \
  --num-envs 1
```

## 2. `task1_reference.py`：直接驱动环境的固定动作脚本

该文件与 `agent.py` 复用了几乎相同的动作序列，但用途不同：它不实现提交 policy，而是直接：

```text
make_env(task_id=..., observation_mode="pixels")
        ↓
env.reset(seed)
        ↓
for action in build_plan(): env.step(action)
        ↓
收集 reward、terminated、terminal_reason、events
```

阅读重点：

- `build_plan()`：把任务路线翻译成像素动作；注释中的 tile 坐标是人工规划时的中间检查点。
- `run()`：正确处理 `terminated` 和 `truncated`，并在 `finally` 中关闭环境。
- 返回字典：展示如何用 `info["game"]["world_completed"]`、`terminal_reason` 和事件记录
  验证一次本地实验是否真的完成。

你应该从这个文件记住两个工程习惯：环境要关闭；任务成功不要只看 reward，而要检查终止原因
或 `world_completed`。

可运行：

```bash
python docs/Mathematical_logic/examples/task1_reference.py
```

当前版本会完成 Task 1；预期会看到 `world_completed=True`。

## 3. `task2_reference.py`：符号规划示例

这是 Python 示例中最重要的一份。它把“原始环境循环”拆为四层：

```text
完整 info（只用于示例）
        ↓ extract_symbolic_state
SymbolicState：玩家、怪物、宝箱、出口、陷阱、钥匙、生命值
        ↓ SymbolicAgent.select_goals / bfs_path_to_goal
tile 级路径与子目标
        ↓ move_one_tile / action_from_step
像素级方向动作，再交给 env.step
```

### 3.1 固定地图常量

文件顶部的 `TASK2_*` 常量描述当前内置 Task 2 的怪物、宝箱、出口和陷阱位置。它们帮助读者
先理解关卡，但也是该参考实现不能泛化的主要原因。最终 Agent 应由视觉识别这些对象，而不是
保留这些坐标常量。

### 3.2 `SymbolicState` 与 `extract_symbolic_state()`

`SymbolicState` 是一个最小的 tile 级世界模型。`extract_symbolic_state()` 将环境信息组装为它：

- 玩家坐标、生命值来自 `info["agent"]`；
- 怪物/宝箱是否仍存在来自 `info["entities"]`；
- 钥匙数来自 `info["inventory"]`；
- 坐标仍由前面的固定常量补充。

这里的价值在于字段设计和“感知层/决策层分离”，而不是字段的取得方式。正式代码中应由
`vision.py` 从 `obs` 填充同类字段。

### 3.3 BFS 与安全格

按这个顺序读工具函数：

1. `neighbors()`、`in_bounds()`、`manhattan()`：网格基础操作；
2. `danger_tiles()`、`is_walkable()`：定义不能踩入的格子；
3. `bfs_path_to_goal()`：队列、`parent` 映射与回溯生成最短路径；
4. `action_from_step()`：把相邻 tile 边映射到 `UP/DOWN/LEFT/RIGHT`。

注意 `bfs_path_to_goal()` 允许目标格作为终点，即使普通移动规则不允许踩入它；而怪物和宝箱
实际使用的是它们的**安全邻接格**作为 goal。这是处理交互对象时最值得迁移的思路。

### 3.4 `SymbolicAgent` 的优先级

`select_goals()` 写出了策略骨架：

1. 有怪物时先靠近怪物；
2. 没有钥匙且有宝箱时靠近宝箱；
3. 否则前往出口。

`act()` 在已经相邻时处理交互：生命值充足时 `ACTION_A` 攻击，否则 `ACTION_B` 防御；若相邻
宝箱则 `ACTION_A` 开箱；其余时候执行 BFS 路径的第一步。

这段代码展示了“先子目标选择，再路径规划，再交互”的分层。它不处理当前项目中更复杂的
多房间记忆、视觉误检、动态机关和 action 队列。

### 3.5 `move_one_tile()` 为什么存在

planner 得到的是 tile 路径，环境接收的却是像素动作。`move_one_tile()` 重复按一个方向，直到
`info["agent"]["position_px"]` 达到下一个 tile 的像素坐标，最多尝试 `TILE_SIZE * 5` 次。

它说明“tile → pixel”不是简单地永远重复 16 次：边界、碰撞和初始像素偏移都可能影响实际
次数。正式代码不能读取这个隐藏像素坐标，因此需要以视觉和 memory 管理动作计划。

### 3.6 `run()`：把策略接回真实环境

`run()` 是完整的实验循环。每轮提取 state、选动作、执行移动/交互、更新怪物命中标记、记录
trace，并在结束时返回摘要。`trace` 很适合学习如何排查“规划路径正确但环境执行失败”。

可运行：

```bash
python docs/Mathematical_logic/examples/task2_reference.py
```

当前版本预期完成 Task 2，并打印 `world_completed=True`。

## 4. `KillMonsterFormalization.lean`：从策略到证明

这是一个独立、可编译的 Lean 4 文件。它的命名空间是 `KillMonsterFormalization`，不依赖
Mathlib，重点是符号层，不试图证明像素分类器或完整游戏引擎。

建议按以下 5 段阅读，而不是逐行硬读：

| 段落 | 核心定义/定理 | 要回答的问题 |
|---|---|---|
| 状态模型 | `Action`、`GoalType`、`Goal`、`SymbolicState` | 要证明的世界由哪些对象和属性构成？ |
| 逻辑谓词 | `adjacent`、`inBounds`、`isSafe`、`canAttack`、`canOpenChest` | 什么叫安全移动、可攻击、可开箱？ |
| 转移语义 | `Step`、`Exec` | 一步动作和一段计划怎样改变状态？ |
| 通用定理 | `safe_move_preserves_safe_state`、`exec_append`、`task_completable_if_subplans_exist` | 怎样组合局部子计划来证明任务可完成？ |
| BFS 与具体见证 | `bfsVisited*`、`task2Init`、`task2_concrete_completable` | 如何说明有限深度搜索覆盖可达状态，并给出 Task 2 的具体成功轨迹？ |

### 4.1 `Step` 与 `Exec`

`Step s a t` 是关系式，而非单个 Python 函数：同一个攻击动作在满足前提时可以选择某个相邻
怪物或宝箱。这避开了 Python set 遍历顺序等实现细节。

`Exec s plan final` 将单步关系递归连接成一段计划。先读 `exec_cons_inv` 和 `exec_append`，
它们是后续组合证明的基础。

### 4.2 两种 BFS 表述

文件先给出抽象版本：`BfsFrontierComplete` 是一个 frontier 覆盖不变量；
`bfs_completeness_from_frontier_invariant` 说明只要该不变量成立，有限步可达的目标一定能在
frontier 中找到。

随后给出可执行版本：

```text
symbolicStepFn → expandFrontier → bfsVisited → bfsVisitedFrom
```

`bfsVisited_frontier_invariant` 和 `bfsVisited_complete_for_bounded_goal` 将这个可执行按深度展开
与有限步可达性连接起来。它没有实现 Python 中的 parent map，也不保证“最短路径重建”；它证明
的是“在深度上界内，不漏掉可达状态”。

### 4.3 具体 Task 2 见证

最后一段把当前简化地图写成常量：`task2Init`、`task2Monster`、`task2Chest`、`task2Exits`，然后：

1. 给出到怪物、到宝箱、到出口的动作列表；
2. 逐段证明 `Exec`；
3. 证明攻击、开箱和最终出口条件；
4. 用 `task2_concrete_completable` 合成 Task 2 可完成性。

它是“一个明确计划为何正确”的证明，不等价于“所有像素输入、所有地图变体上的神经网络都正确”。

可检查：

```bash
lean docs/Mathematical_logic/examples/KillMonsterFormalization.lean
```

仓库的 `lean-toolchain` 固定了 Lean 版本；若 shell 找不到 `lean`，可使用：

```bash
/home/jjj/.elan/bin/lean docs/Mathematical_logic/examples/KillMonsterFormalization.lean
```

## 5. `txt`：目录的旧版简要索引

`txt` 是简短说明，列出两个 Python 示例的运行命令与三个学习目标。它适合作为速查表；本文件
补充了代码层级、限制条件与 Lean 部分，因此建议以本指南为主。

## 6. 根据你的目标选择阅读路径

### 我只想知道如何写能被测评器加载的 Agent

读 `agent.py`，然后阅读课程测评说明中的 policy 接口。重点掌握 `Policy`、`reset`、`act` 和
`make_policy`，不要复制固定动作列表。

### 我想理解 planner / controller 应该怎么组织

读 `task2_reference.py` 的 `SymbolicState`、工具函数、`SymbolicAgent`、`run()`；再对照
`submissions/planner.py` 和 `submissions/controllers/task3.py`，看项目正式版本如何去掉硬编码坐标、
加入 memory 与跨房间探索。

### 我想写 Lean 证明

先读 `KillMonsterFormalization.lean` 的 `SymbolicState`、`Step`、`Exec`、`exec_append`，再读
`task_completable_if_subplans_exist`；最后对照 `submissions/lean/` 中当前提交的环境、策略契约和
Task 3 定理。

### 我想调试某个环境任务

先运行 `task1_reference.py` 或 `task2_reference.py`，阅读它们返回的 events/trace；再使用
`utils/evaluate_policy.py --info-mode full` 进行本地诊断。提交前必须切回 `--info-mode safe`。

## 7. 建议的主动练习

1. 修改 `task1_reference.py` 的一个动作次数，观察 `events` 中的 `action_blocked` 与任务失败如何出现。
2. 在 `task2_reference.py` 中打印 BFS 返回的 tile path，手算其长度是否符合地图布局。
3. 把 `TASK2_CHEST` 改成错误坐标，理解“固定常量”为什么不能代替视觉。
4. 在 Lean 文件中从 `task2_exec_to_monster` 开始，跟踪每一个 `Step.moveSafe` 的前提如何由 `simp`/`decide` 完成。
5. 对比示例的 `is_walkable()` 与正式 `submissions/planner.py:is_safe_tile()`，列出正式版本额外处理的 bridge、gap、opened chest 和 NPC。
