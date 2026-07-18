# What E Have Done

## 1. 当前负责范围与正式提交位置

E 负责 Task 4 / Task 5 的任务链控制器，以及第二阶段中对应的 Lean 组合证明与评测结果整理：

- `submissions/controllers/task4.py`：旋转桥、钥匙、剑、南侧守卫、中央最终宝箱。
- `submissions/controllers/task5.py`：多房间探索、按钮、钥匙、治疗、四宝箱与 HP 预算。
- `submissions/lean/TaskProofs.lean`：Task 4/5 阶段优先级、完成链，以及 Task 3/4/5 共享组合引理。
- `results/e/`：Task 4/5 的 `safe` 评测 JSON 与里程碑截图证据。

### E 工作完成结论

按现有分工，E 的交付已经完成：

- 第一阶段 Task 4 / Task 5 controller 已放入 `submissions/`，包内相对导入正确；
- 正式 `safe` 模式下 seed=0 两端到端通过，并保存 JSON 与里程碑截图；
- 第二阶段 Task 4/5 阶段证明与完成链、Task 3/4/5 组合引理已通过 `lake build`；
- 评测命令、结果数字与截图路径已整理进本文档，可供报告直接引用。


正式 Python 入口为 `submissions.student_policy:make_policy`。正式 `safe` 评测应使用
task-specific 绑定，否则共享 `--policy` 收不到 `task_id`，会落不到 Task 4/5 controller：

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_4 mathematical_logic/task_5 \
  --task-policy mathematical_logic/task_4=submissions.student_policy:make_policy \
  --task-policy mathematical_logic/task_5=submissions.student_policy:make_policy \
  --num-envs 1 \
  --info-mode safe \
  --json-out results/e/task45_seed0.json
```

---

## 2. 信息边界

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

控制器内导入约定：

```python
from ..planner import actions_for_tile_path, bfs_path, bfs_path_to_adjacent_target
from ..state import AgentMemory, Position, SymbolicState
```

入口侧使用绝对包路径：`from submissions.controllers import make_controller` 等。

依赖的已有模块（只调用、不改其未完成项）：

| 模块 | 用途 |
|------|------|
| `submissions/vision*.py` | 玩家/墙/箱/怪/出口；按钮/开关/桥/gap |
| `submissions/planner.py` | `bfs_path`、邻接目标、tile→原子动作 |
| `submissions/student_policy.py` | Policy 入口与按 `task_id` 分派 controller |

---

## 3. Task 4：旋转桥任务链

### 3.1 目标与房间顺序

按资源推进，而不是固定脚本走完整张图：

1. 无钥匙：桥朝北 → 北房开箱拿钥匙；
2. 有钥匙无剑：桥朝东 → 东房开箱拿剑；
3. 有剑：桥朝南 → 南房击败守卫；
4. 守卫确认已死后：回中央，打开揭示出的最终宝箱，触发 `world_completed`。

房间由可见出口方向推断（不读隐藏 room id）。中央房间的 gap 用当前桥布局对应的
可通行 tile 补进 planner；开关在西房，视觉漏检时回退到 `(4, 4)`。

### 3.2 守卫击败判定

当前规则：

- 仅在 **南房** 记录“见过/打过守卫”（`t4saw_guardian` / `t4attacked`）；
- 南房内怪物集合变空后才置 `t4guard`；
- 相邻攻击达到有限次数后也会强制进入 `t4guard`，避免误检拖死；
- `t4guard` 后优先回中央，对最终宝箱（或 hub `(4, 4)`）面向后开箱。

### 3.3 主要 memory 标志

| 标志 | 含义 |
|------|------|
| `t4bridge` | 当前桥状态估计：`west_to_north` / `west_to_east` / `west_to_south` |
| `t4post` | 持剑后子流程阶段（离东、切桥、过桥、击杀等） |
| `t4guard` | 守卫已确认击败，转入最终宝箱 |
| `t4saw_guardian` / `t4attacked` / `t4attack_hits` | 南房战斗进度 |

---

## 4. Task 5：多房间 + HP 预算

### 4.1 阶段顺序

用 `memory.notes` 串行推进，前一阶段完成才进入下一阶段：

```text
t5btn → t5key → t5gate / t5healed → t5sgold → t5wgold
```

对应行为：

1. 踩起点按钮开南门；
2. 南侧开钥匙箱，护盾北穿返回；
3. 开东门进入东房，打开治疗箱；
4. 回起点开金箱；
5. 进西房开最后金箱，触发 `world_completed`（需累计打开 4 个宝箱）。

### 4.2 HP 与脚本段

环境约每 200 步掉 1 HP。因此策略重点是少受伤、阶段不乱序。纯 BFS 不稳的几段保留
固定动作序列：

| 脚本 | 作用 |
|------|------|
| `NORTH_CROSS` | 南侧北出口护盾穿越，减少 chaser 扣血 |
| `EAST_GATE_BURST` | 有钥匙后冲东门 |
| `WEST_GOLD_SCRIPT` | 西房绕 NPC 到底行再开金箱 |

危险格规避示例：起点西行屏蔽 chaser/NPC 相关格；南侧屏蔽固定阻挡格并并上动态怪物格。
按钮必须 **踩上去** 触发，不是邻接按 `ACTION_A`。

---

## 5. Python 验证结果

结果保存在 `results/e/`。

### 5.1 Task 4 / Task 5（seed=0，safe）

```bash
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_4 mathematical_logic/task_5 \
  --task-policy mathematical_logic/task_4=submissions.student_policy:make_policy \
  --task-policy mathematical_logic/task_5=submissions.student_policy:make_policy \
  --num-envs 1 \
  --info-mode safe \
  --json-out results/e/task45_seed0.json
```

| 任务 | success | steps | reward | terminal_reason | JSON |
|------|---------|------:|-------:|-----------------|------|
| task_4 | True | 1137 | 264.630 | world_completed | `results/e/task4_seed0.json` / `task45_seed0.json` |
| task_5 | True | 1152 | 162.330 | world_completed | `results/e/task5_seed0.json` / `task45_seed0.json` |

Task 4 里程碑：`switch_activated`、`key_collected`、`door_opened`、`item_collected`、
`monster_killed`、`gold_collected`、`world_completed`。

Task 5 里程碑：`button_pressed`、`key_collected`、`door_opened`、`agent_healed`、
`gold_collected`、`chest_opened` 合计 4 次、`world_completed`。

### 5.2 单独重跑

```bash
# 仅 Task 4
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_4 \
  --task-policy mathematical_logic/task_4=submissions.student_policy:make_policy \
  --num-envs 1 --info-mode safe --json-out results/e/task4_seed0.json

# 仅 Task 5
python utils/evaluate_policy.py \
  --tasks mathematical_logic/task_5 \
  --task-policy mathematical_logic/task_5=submissions.student_policy:make_policy \
  --num-envs 1 --info-mode safe --json-out results/e/task5_seed0.json
```

---

## 6. 可复现截图证据

使用 `utils/capture_policy_evidence.py`，在正式 `safe_info` 下于首次出现关键事件时保存
渲染帧和 `manifest.json`。

### 6.1 Task 4

```bash
python utils/capture_policy_evidence.py \
  --policy submissions.student_policy:make_policy \
  --task mathematical_logic/task_4 \
  --seed 0 \
  --output-dir results/e/task4_seed0_evidence \
  --milestones switch_activated key_collected item_collected door_opened \
               monster_killed chest_opened chest_revealed gold_collected world_completed
```

轨迹：成功，1137 steps，reward 264.630。关键帧：

| 文件 | 事件 | step |
|------|------|-----:|
| `00_start.png` | start | 0 |
| `01_key_collected.png` | key_collected | 177 |
| `03_switch_activated.png` | switch_activated | 370 |
| `04_door_opened.png` | door_opened | 562 |
| `05_item_collected.png` | item_collected（剑） | 611 |
| `06_monster_killed.png` | monster_killed | 1031 |
| `07_chest_revealed.png` | chest_revealed | 1031 |
| `08_gold_collected.png` / `09_world_completed.png` | 通关 | 1137 |

详见 `results/e/task4_seed0_evidence/manifest.json`。

### 6.2 Task 5

```bash
python utils/capture_policy_evidence.py \
  --policy submissions.student_policy:make_policy \
  --task mathematical_logic/task_5 \
  --seed 0 \
  --output-dir results/e/task5_seed0_evidence \
  --milestones button_pressed key_collected chest_opened door_opened \
               agent_healed gold_collected world_completed
```

轨迹：成功，1152 steps，reward 162.330。关键帧：

| 文件 | 事件 | step |
|------|------|-----:|
| `00_start.png` | start | 0 |
| `01_button_pressed.png` | button_pressed | 88 |
| `02_key_collected.png` | key_collected | 259 |
| `04_door_opened.png` | door_opened | 516 |
| `05_agent_healed.png` | agent_healed | 629 |
| `06_gold_collected.png` | gold_collected | 886 |
| `07_world_completed.png` | world_completed | 1152 |

详见 `results/e/task5_seed0_evidence/manifest.json`。

---

## 7. Lean 形式化与证明

工具链由 `lean-toolchain` 固定为 `leanprover/lean4:v4.29.0-rc6`。E 在共享
`submissions/lean/TaskProofs.lean` 中补充 Task 4/5 与组合部分（环境与 planner 契约文件
由项目共用）。

### 7.1 Task 4

- `task4Phase`：开箱 → 持剑打守卫 → 操作开关 → 导航；
- `Task4Done`：`monsters = [] ∧ keys > 0 ∧ gold > 0`；
- `BridgeWalkable`：gap 上需有 bridge 才可走；
- 定理：`task4_chest_priority`、`task4_attack_after_chests_with_sword`、
  `task4_switch_when_no_chest_or_fight`、`task4_navigate_otherwise`、
  `task4_gap_requires_bridge`、`task4_key_sword_kill_chest_chain`。

### 7.2 Task 5

- `task5Phase`：未按按钮 → 开箱 → 清挡路怪物 → 导航；
- `Task5Done`：无未开宝箱且 `keys > 0 ∧ gold > 0`；
- 定理：`task5_button_priority`、`task5_chest_after_buttons`、
  `task5_clear_monster_when_blocked`、`task5_navigate_when_local_goals_done`、
  `task5_button_key_chests_chain`。

### 7.3 Task 3/4/5 组合

- `task345_share_adjacent_interaction`
- `task3_done_implies_key` / `task4_done_implies_key` / `task5_done_implies_key`

证明边界：基于符号状态层，不证明像素分类器对所有图像正确；不把搜索完备性伪装成
`axiom`。

### 7.4 编译验证

```bash
lake build
lake env lean submissions/lean/TaskProofs.lean
```

两条命令均通过。

---





