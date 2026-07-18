from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .state import Position
from .vision_preprocess import ROBUST_CHANNELS, extract_tile_batch, robust_channels


TileLabel = str

TILE_SIZE = 16
ROOM_WIDTH_TILES = 10
ROOM_HEIGHT_TILES = 8

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "models" / "static_tile_multitask.pt"

# Public IDs intentionally match the environment's documented object IDs.
LABEL_NAMES: tuple[TileLabel, ...] = (
    "floor",
    "wall",
    "chest_key",
    "chest_gold",
    "chest_heal",
    "chest_item",
    "trap_spike",
    "trap_abyss",
    "npc",
    "gap",
    "bridge",
    "button",
    "switch",
    "exit_normal",
    "exit_locked_key",
    "exit_conditional",
    "monster_chaser",
    "monster_patroller",
    "monster_ambusher",
    "player",
)

LABEL_TO_INDEX = {name: index for index, name in enumerate(LABEL_NAMES)}
INDEX_TO_LABEL = {index: name for name, index in LABEL_TO_INDEX.items()}
STATIC_LABELS = LABEL_NAMES
STATIC_CLASS_TO_INDEX = LABEL_TO_INDEX
STATIC_INDEX_TO_CLASS = INDEX_TO_LABEL

TERRAIN_NAMES = ("floor", "wall", "trap_spike", "trap_abyss", "gap", "bridge")
OBJECT_NAMES = ("none", "chest", "npc", "button", "switch", "exit")
CHEST_NAMES = ("none", "chest_key", "chest_gold", "chest_heal", "chest_item")
EXIT_NAMES = ("none", "exit_normal", "exit_locked_key", "exit_conditional")
STATE_NAMES = ("default", "changed")


@dataclass(frozen=True)
class StaticVisionResult:
    walls: set[Position]
    floors: set[Position]
    chests: set[Position]
    opened_chests: set[Position]
    exits: set[Position]
    chest_types: dict[Position, TileLabel]
    exit_types: dict[Position, TileLabel]
    traps: set[Position]
    buttons: set[Position]
    pressed_buttons: set[Position]
    switches: set[Position]
    activated_switches: set[Position]
    bridges: set[Position]
    gaps: set[Position]
    labels: dict[Position, TileLabel]
    label_ids: dict[Position, int]
    confidences: dict[Position, float]
    uncertain: set[Position]
    backend: str


class StaticMultiHeadCNN:
    """Factory for the batched tile network without importing torch eagerly."""

    def __new__(cls, nn: Any):  # noqa: D102
        class ResidualBlock(nn.Module):
            def __init__(self, channels: int) -> None:
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                )
                self.relu = nn.ReLU(inplace=True)

            def forward(self, x):  # noqa: ANN001
                return self.relu(x + self.layers(x))

        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.features = nn.Sequential(
                    nn.Conv2d(ROBUST_CHANNELS, 24, 3, padding=1, bias=False),
                    nn.BatchNorm2d(24),
                    nn.ReLU(inplace=True),
                    ResidualBlock(24),
                    nn.Conv2d(24, 40, 3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(40),
                    nn.ReLU(inplace=True),
                    ResidualBlock(40),
                    nn.Conv2d(40, 64, 3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                    nn.AdaptiveAvgPool2d((1, 1)),
                )
                self.dropout = nn.Dropout(0.08)
                self.terrain_head = nn.Linear(64, len(TERRAIN_NAMES))
                self.object_head = nn.Linear(64, len(OBJECT_NAMES))
                self.chest_head = nn.Linear(64, len(CHEST_NAMES))
                self.exit_head = nn.Linear(64, len(EXIT_NAMES))
                self.state_head = nn.Linear(64, len(STATE_NAMES))

            def forward(self, x):  # noqa: ANN001
                features = self.dropout(self.features(x).flatten(1))
                return {
                    "terrain": self.terrain_head(features),
                    "object": self.object_head(features),
                    "chest": self.chest_head(features),
                    "exit": self.exit_head(features),
                    "state": self.state_head(features),
                }

        return Model()


class BatchedStaticClassifier:
    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS_PATH) -> None:
        self.weights_path = weights_path
        self.model: Any | None = None
        self.torch: Any | None = None
        self.backend = "rules"
        self._load()

    def _load(self) -> None:
        if not self.weights_path.exists():
            return
        try:
            import torch
            from torch import nn

            model = StaticMultiHeadCNN(nn)
            payload = torch.load(self.weights_path, map_location="cpu", weights_only=False)
            state_dict = payload.get("model_state_dict", payload)
            model.load_state_dict(state_dict)
            model.eval()
            self.model = model
            self.torch = torch
            self.backend = "multitask_cnn"
        except (ImportError, OSError, RuntimeError, KeyError, ValueError):
            self.model = None
            self.torch = None
            self.backend = "rules"

    def classify_batch(self, tiles: np.ndarray) -> dict[str, np.ndarray]:
        if self.model is None or self.torch is None:
            return _classify_batch_rules(tiles)
        tensor = self.torch.from_numpy(robust_channels(tiles))
        with self.torch.inference_mode():
            logits = self.model(tensor)
            output: dict[str, np.ndarray] = {}
            for name, values in logits.items():
                output[name] = self.torch.softmax(values, dim=1).cpu().numpy()
        return output


_CLASSIFIER: BatchedStaticClassifier | None = None


def get_static_classifier() -> BatchedStaticClassifier:
    global _CLASSIFIER
    if _CLASSIFIER is None:
        _CLASSIFIER = BatchedStaticClassifier()
    return _CLASSIFIER


def reset_static_classifier() -> None:
    global _CLASSIFIER
    _CLASSIFIER = None


def extract_static_tiles(obs: np.ndarray) -> StaticVisionResult:
    """Classify all 80 map tiles in one model call."""

    classifier = get_static_classifier()
    tiles = extract_tile_batch(obs)
    probabilities = classifier.classify_batch(tiles)

    walls: set[Position] = set()
    floors: set[Position] = set()
    chests: set[Position] = set()
    opened_chests: set[Position] = set()
    exits: set[Position] = set()
    chest_types: dict[Position, TileLabel] = {}
    exit_types: dict[Position, TileLabel] = {}
    traps: set[Position] = set()
    buttons: set[Position] = set()
    pressed_buttons: set[Position] = set()
    switches: set[Position] = set()
    activated_switches: set[Position] = set()
    bridges: set[Position] = set()
    gaps: set[Position] = set()
    labels: dict[Position, TileLabel] = {}
    label_ids: dict[Position, int] = {}
    confidences: dict[Position, float] = {}
    uncertain: set[Position] = set()

    for index in range(ROOM_WIDTH_TILES * ROOM_HEIGHT_TILES):
        pos = (index % ROOM_WIDTH_TILES, index // ROOM_WIDTH_TILES)
        terrain_index = int(probabilities["terrain"][index].argmax())
        object_index = int(probabilities["object"][index].argmax())
        chest_index = int(probabilities["chest"][index].argmax())
        exit_index = int(probabilities["exit"][index].argmax())
        state_index = int(probabilities["state"][index].argmax())

        terrain = TERRAIN_NAMES[terrain_index]
        obj = OBJECT_NAMES[object_index]
        label = terrain
        confidence = float(probabilities["terrain"][index, terrain_index])
        exit_head_confidence = float(probabilities["exit"][index, exit_index])
        exit_object_confidence = float(
            probabilities["object"][index, OBJECT_NAMES.index("exit")]
        )
        exit_head_supported = (
            is_boundary_tile(pos)
            and exit_index != EXIT_NAMES.index("none")
            and exit_head_confidence >= 0.82
            and exit_object_confidence >= 0.08
        )

        if obj == "chest" and not exit_head_supported:
            label = CHEST_NAMES[chest_index]
            if label == "none":
                label = "chest_item"
            chests.add(pos)
            chest_types[pos] = label
            if state_index == 1:
                opened_chests.add(pos)
            confidence = min(
                float(probabilities["object"][index, object_index]),
                float(probabilities["chest"][index, chest_index]),
            )
        elif (obj == "exit" or exit_head_supported) and is_boundary_tile(pos):
            label = EXIT_NAMES[exit_index]
            if label == "none":
                label = "exit_normal"
            exits.add(pos)
            exit_types[pos] = label
            confidence = min(
                max(
                    float(probabilities["object"][index, object_index]),
                    exit_object_confidence,
                ),
                exit_head_confidence,
            )
        elif obj == "npc":
            label = "npc"
            confidence = float(probabilities["object"][index, object_index])
        elif obj == "button":
            label = "button"
            buttons.add(pos)
            if state_index == 1:
                pressed_buttons.add(pos)
            confidence = float(probabilities["object"][index, object_index])
        elif obj == "switch":
            label = "switch"
            switches.add(pos)
            if state_index == 1:
                activated_switches.add(pos)
            confidence = float(probabilities["object"][index, object_index])

        if terrain == "wall":
            walls.add(pos)
        elif terrain in {"trap_spike", "trap_abyss"}:
            traps.add(pos)
            if terrain == "trap_abyss":
                gaps.add(pos)
        elif terrain == "gap":
            gaps.add(pos)
        elif terrain == "bridge":
            bridges.add(pos)

        if terrain not in {"wall", "gap", "trap_abyss"}:
            floors.add(pos)
        labels[pos] = label
        label_ids[pos] = LABEL_TO_INDEX[label]
        confidences[pos] = confidence
        if confidence < 0.45:
            uncertain.add(pos)

    return StaticVisionResult(
        walls=walls,
        floors=floors,
        chests=chests,
        opened_chests=opened_chests,
        exits=exits,
        chest_types=chest_types,
        exit_types=exit_types,
        traps=traps,
        buttons=buttons,
        pressed_buttons=pressed_buttons,
        switches=switches,
        activated_switches=activated_switches,
        bridges=bridges,
        gaps=gaps,
        labels=labels,
        label_ids=label_ids,
        confidences=confidences,
        uncertain=uncertain,
        backend=classifier.backend,
    )


def _classify_batch_rules(tiles: np.ndarray) -> dict[str, np.ndarray]:
    """Conservative fallback used only when trained weights are unavailable."""

    count = len(tiles)
    result = {
        "terrain": np.zeros((count, len(TERRAIN_NAMES)), dtype=np.float32),
        "object": np.zeros((count, len(OBJECT_NAMES)), dtype=np.float32),
        "chest": np.zeros((count, len(CHEST_NAMES)), dtype=np.float32),
        "exit": np.zeros((count, len(EXIT_NAMES)), dtype=np.float32),
        "state": np.zeros((count, len(STATE_NAMES)), dtype=np.float32),
    }
    for values in result.values():
        values[:, 0] = 1.0

    for index, tile in enumerate(tiles):
        dark = tile.mean(axis=-1) < 18
        red = tile[..., 0].astype(np.int16)
        green = tile[..., 1].astype(np.int16)
        blue = tile[..., 2].astype(np.int16)
        wall_pixels = (red > green + 70) & (red > blue + 40)
        wood_pixels = (red > 90) & (red > green * 1.35) & (green > blue)
        metal_pixels = (np.max(tile, axis=-1) - np.min(tile, axis=-1) < 18) & (red > 100)
        if dark.mean() > 0.82:
            result["terrain"][index] = 0
            result["terrain"][index, TERRAIN_NAMES.index("trap_abyss")] = 1
        elif wall_pixels.sum() > 80:
            result["terrain"][index] = 0
            result["terrain"][index, TERRAIN_NAMES.index("wall")] = 1
        elif metal_pixels.sum() > 14:
            result["terrain"][index] = 0
            result["terrain"][index, TERRAIN_NAMES.index("trap_spike")] = 1
        elif wood_pixels.sum() > 28:
            result["object"][index] = 0
            result["object"][index, OBJECT_NAMES.index("chest")] = 1
            result["chest"][index] = 0
            result["chest"][index, CHEST_NAMES.index("chest_item")] = 1
    return result


def is_boundary_tile(pos: Position) -> bool:
    x, y = pos
    return x in {0, ROOM_WIDTH_TILES - 1} or y in {0, ROOM_HEIGHT_TILES - 1}


def is_chest_label(label: str) -> bool:
    return label.startswith("chest_")


def is_exit_label(label: str) -> bool:
    return label.startswith("exit_")


def color_mask(tile: np.ndarray, color: tuple[int, int, int], *, tolerance: int) -> np.ndarray:
    target = np.asarray(color, dtype=np.int16)
    delta = np.abs(tile.astype(np.int16) - target)
    return np.max(delta, axis=-1) <= tolerance


def count_near_color(tile: np.ndarray, color: tuple[int, int, int], *, tolerance: int) -> int:
    return int(color_mask(tile, color, tolerance=tolerance).sum())
