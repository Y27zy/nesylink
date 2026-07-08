# Stage 1 B 视觉接口说明

B 负责把 raw pixel observation 识别成 `SymbolicState` 中的基础视觉字段。当前实现分两层：

- StaticNet：tile 级静态物体识别。
- DynamicNet：整图动态对象识别。

## 对外接口

其他同学不要直接调用模型，统一调用：

```python
from vision import extract_symbolic_state

state = extract_symbolic_state(obs, memory, inventory=inventory)
```

该函数会填充：

- `state.player: tuple[int, int] | None`
- `state.walls: set[tuple[int, int]]`
- `state.floors: set[tuple[int, int]]`
- `state.chests: set[tuple[int, int]]`
- `state.opened_chests: set[tuple[int, int]]`
- `state.exits: set[tuple[int, int]]`
- `state.monsters: set[tuple[int, int]]`

坐标均为 tile 坐标 `(x, y)`，其中 `x in 0..9`，`y in 0..7`。

## StaticNet

静态识别在 `vision_static_resnet.py` 中，输入是单个 `16 x 16` tile。

```python
from vision_static_resnet import extract_static_tiles

result = extract_static_tiles(obs)
```

当前实现是 ResNet-ready：

- 如果存在 `models/static_tile_resnet.pt` 且安装了 PyTorch，则使用 Tiny ResNet 做 tile 分类。
- 如果没有权重或没有 PyTorch，则自动使用颜色规则兜底，保证 Agent 仍可运行。

如果存在 `models/static_tile_resnet.pt` 且安装了 PyTorch，则使用 Tiny ResNet 做 tile 分类。否则使用颜色规则兜底。

分类标签：

```text
floor, wall, chest, exit, unknown
```

StaticNet 不负责玩家和怪物，因为它们是连续移动实体，可能跨 tile。

## DynamicNet

动态识别在 `vision_dynamic_resnet.py` 中，输入是完整 `128 x 160 x 3` 画面。

```python
from vision_dynamic_resnet import extract_dynamic_objects

result = extract_dynamic_objects(obs)
```

如果存在 `models/dynamic_pixel_resnet.pt` 且安装了 PyTorch，则使用像素级 heatmap 网络。否则使用颜色、形状和连通域规则兜底。

动态类别：

```text
player, monster_chaser, monster_patroller, monster_ambusher
```

## 给 planner/controller 的约定

- `state.walls`、`state.chests` 和 `state.monsters` 默认视为阻挡移动或危险目标。
- `state.exits` 同时会加入 `state.floors`，planner 可以把它当成目标格。
- 如果 `state.player is None`，说明视觉没有识别到玩家，controller 应该返回 `WAIT` 或使用 memory 中的上一帧位置。
- `state.raw_features["static_vision_backend"]` 会显示当前使用 `"resnet"` 还是 `"rules"`，只用于调试和报告。
- `state.raw_features["dynamic_vision_backend"]` 会显示当前使用 `"resnet"` 还是 `"components"`，只用于调试和报告。

## 硬编码视觉评测

开发阶段可以使用下面的命令，将像素识别结果与环境运行时真值进行离线对照：

```bash
python utils/evaluate_vision.py --random-steps 60 --seed 0
```

这个脚本会评测墙、宝箱、出口、按钮、开关、桥、缺口、陷阱、玩家和怪物。它可以读取隐藏运行时状态，但只允许用于开发、调试和报告，最终 `agent.py` 仍然只能从 pixels 和允许的 inventory 信息构造符号状态。

## 不允许的事

最终推理时不要用以下隐藏信息替代视觉识别：

```python
info["agent"]["tile"]
info["env"]["room_id"]
info["entities"]
info["dynamic"]
```

调试阶段可以用它们做识别准确率对齐检查，但报告里需要说明用途。
