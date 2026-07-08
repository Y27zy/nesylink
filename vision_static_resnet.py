from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from state import Position


TileLabel = str

TILE_SIZE = 16
ROOM_WIDTH_TILES = 10
ROOM_HEIGHT_TILES = 8

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "models" / "static_tile_resnet.pt"

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

STATIC_LABELS = LABEL_NAMES
STATIC_CLASS_TO_INDEX = {label: index for index, label in enumerate(STATIC_LABELS)}
STATIC_INDEX_TO_CLASS = {index: label for label, index in STATIC_CLASS_TO_INDEX.items()}
LABEL_TO_INDEX = STATIC_CLASS_TO_INDEX
INDEX_TO_LABEL = STATIC_INDEX_TO_CLASS


PALETTE: dict[str, tuple[int, int, int]] = {
    "outline": (8, 8, 16),
    "highlight": (255, 244, 112),
    "shadow": (42, 45, 88),
    "floor_light": (72, 122, 248),
    "floor_dark": (36, 82, 206),
    "floor_darker": (24, 52, 138),
    "wall_light": (255, 86, 146),
    "wall_mid": (219, 18, 82),
    "wall_dark": (88, 0, 36),
    "wall_edge": (255, 44, 112),
    "player_tunic": (36, 198, 72),
    "player_tunic_light": (126, 248, 82),
    "player_face": (240, 154, 52),
    "player_hair": (86, 42, 18),
    "chest_wood": (152, 82, 36),
    "chest_band": (255, 216, 80),
    "chest_inner": (42, 18, 16),
    "door_wood": (96, 48, 26),
    "exit_glow": (255, 244, 112),
    "coin": (210, 28, 96),
    "heart": (204, 16, 72),
}


@dataclass(frozen=True)
class StaticVisionResult:
    walls: set[Position]
    floors: set[Position]
    chests: set[Position]
    opened_chests: set[Position]
    exits: set[Position]
    chest_types: dict[Position, TileLabel]
    exit_types: dict[Position, TileLabel]
    labels: dict[Position, TileLabel]
    label_ids: dict[Position, int]
    confidences: dict[Position, float]
    backend: str


class OptionalResNetTileClassifier:
    """Small ResNet-style tile classifier with a rule fallback.

    If `models/static_tile_resnet.pt` exists and PyTorch is available, this
    class uses it. Otherwise it uses deterministic color rules. This keeps the
    submission runnable before training weights are ready.
    """

    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS_PATH) -> None:
        self.weights_path = weights_path
        self.model: Any | None = None
        self.torch: Any | None = None
        self.backend = "rules"
        self._try_load_resnet()

    def classify(
        self,
        tile: np.ndarray,
        *,
        allow_exit: bool = True,
    ) -> tuple[TileLabel, float]:
        if self.model is not None and self.torch is not None:
            label, confidence = self._classify_with_resnet(tile)
            if label != "exit" or allow_exit:
                return label, confidence
        return classify_static_tile_rules(tile, allow_exit=allow_exit)

    def _try_load_resnet(self) -> None:
        if not self.weights_path.exists():
            return
        try:
            import torch
            from torch import nn
        except Exception:
            return

        try:
            model = TinyResNet(num_classes=len(STATIC_LABELS), nn=nn)
            payload = torch.load(self.weights_path, map_location="cpu")
            state_dict = payload.get("model_state_dict", payload) if isinstance(payload, dict) else payload
            model.load_state_dict(state_dict)
            model.eval()
            self.model = model
            self.torch = torch
            self.backend = "resnet"
        except Exception:
            self.model = None
            self.torch = None
            self.backend = "rules"

    def _classify_with_resnet(self, tile: np.ndarray) -> tuple[TileLabel, float]:
        assert self.model is not None
        assert self.torch is not None

        tensor = self.torch.from_numpy(tile.astype(np.float32) / 255.0)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)
        with self.torch.no_grad():
            logits = self.model(tensor)
            probs = self.torch.softmax(logits, dim=1)[0]
            index = int(self.torch.argmax(probs).item())
            confidence = float(probs[index].item())
        return STATIC_INDEX_TO_CLASS.get(index, "unknown"), confidence


class TinyResNet:
    """A tiny ResNet implementation without importing torch at module import time."""

    def __new__(cls, num_classes: int, nn: Any):  # noqa: D102
        class ResidualBlock(nn.Module):
            def __init__(self, channels: int) -> None:
                super().__init__()
                self.block = nn.Sequential(
                    nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                )
                self.relu = nn.ReLU(inplace=True)

            def forward(self, x):  # noqa: ANN001
                return self.relu(x + self.block(x))

        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.stem = nn.Sequential(
                    nn.Conv2d(3, 32, kernel_size=3, padding=1, bias=False),
                    nn.BatchNorm2d(32),
                    nn.ReLU(inplace=True),
                )
                self.blocks = nn.Sequential(
                    ResidualBlock(32),
                    ResidualBlock(32),
                    nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                    ResidualBlock(64),
                )
                self.pool = nn.AdaptiveAvgPool2d((1, 1))
                self.fc = nn.Linear(64, num_classes)

            def forward(self, x):  # noqa: ANN001
                x = self.stem(x)
                x = self.blocks(x)
                x = self.pool(x).flatten(1)
                return self.fc(x)

        return Model()


_CLASSIFIER: OptionalResNetTileClassifier | None = None


def get_static_classifier() -> OptionalResNetTileClassifier:
    global _CLASSIFIER
    if _CLASSIFIER is None:
        _CLASSIFIER = OptionalResNetTileClassifier()
    return _CLASSIFIER


def extract_static_tiles(obs: np.ndarray) -> StaticVisionResult:
    """Recognize B-owned static symbols from a raw pixel observation."""

    classifier = get_static_classifier()
    labels: dict[Position, TileLabel] = {}
    label_ids: dict[Position, int] = {}
    confidences: dict[Position, float] = {}
    walls: set[Position] = set()
    floors: set[Position] = set()
    chests: set[Position] = set()
    opened_chests: set[Position] = set()
    exits: set[Position] = set()
    chest_types: dict[Position, TileLabel] = {}
    exit_types: dict[Position, TileLabel] = {}
    for y in range(ROOM_HEIGHT_TILES):
        for x in range(ROOM_WIDTH_TILES):
            pos = (x, y)
            tile = obs[
                y * TILE_SIZE : (y + 1) * TILE_SIZE,
                x * TILE_SIZE : (x + 1) * TILE_SIZE,
            ]
            if is_open_chest_tile(tile):
                label = classify_chest_type(tile)
                labels[pos] = label
                label_ids[pos] = LABEL_TO_INDEX[label]
                confidences[pos] = 1.0
                opened_chests.add(pos)
                chest_types[pos] = label
                continue
            label, confidence = classifier.classify(
                tile,
                allow_exit=is_boundary_tile(pos),
            )
            labels[pos] = label
            label_ids[pos] = LABEL_TO_INDEX.get(label, LABEL_TO_INDEX["floor"])
            confidences[pos] = confidence

            if label == "wall":
                walls.add(pos)
            elif is_chest_label(label):
                chests.add(pos)
                chest_types[pos] = label
            elif is_exit_label(label):
                exits.add(pos)
                exit_types[pos] = label
                floors.add(pos)
            elif label == "floor":
                floors.add(pos)

    for y in range(ROOM_HEIGHT_TILES):
        for x in range(ROOM_WIDTH_TILES):
            pos = (x, y)
            if pos not in walls and pos not in chests and pos not in opened_chests:
                floors.add(pos)

    return StaticVisionResult(
        walls=walls,
        floors=floors,
        chests=chests,
        opened_chests=opened_chests,
        exits=exits,
        chest_types=chest_types,
        exit_types=exit_types,
        labels=labels,
        label_ids=label_ids,
        confidences=confidences,
        backend=classifier.backend,
    )


def classify_static_tile_rules(
    tile: np.ndarray,
    *,
    allow_exit: bool = True,
) -> tuple[TileLabel, float]:
    counts = {
        name: count_near_color(tile, color, tolerance=14)
        for name, color in PALETTE.items()
    }

    wall_score = (
        counts["wall_mid"]
        + counts["wall_light"]
        + counts["wall_dark"]
        + counts["wall_edge"]
    ) / tile.size * 3
    chest_score = (
        counts["chest_wood"]
        + counts["chest_band"]
        + counts["chest_inner"]
    ) / tile.size * 3
    exit_score = (
        counts["door_wood"]
        + counts["exit_glow"]
        + counts["shadow"]
    ) / tile.size * 3
    floor_score = (
        counts["floor_light"]
        + counts["floor_dark"]
        + counts["floor_darker"]
    ) / tile.size * 3

    if wall_score > 0.22:
        return "wall", min(1.0, wall_score * 3)

    closed_chest_band = count_near_color(
        tile[4:7],
        PALETTE["chest_band"],
        tolerance=14,
    )
    has_closed_chest = counts["chest_wood"] > 25 and closed_chest_band > 18
    if has_closed_chest:
        return classify_chest_type(tile), min(1.0, chest_score * 5)

    if allow_exit:
        # Exits always occupy boundary tiles. This prevents bridge planks and
        # chest bands from being mistaken for doors.
        locked_exit = counts["door_wood"] > 25 and counts["outline"] > 20
        conditional_exit = (
            counts["exit_glow"] > 12
            and counts["outline"] > 30
            and counts["chest_band"] > 20
            and counts["chest_wood"] < 10
        )
        normal_exit = (
            counts["exit_glow"] > 12
            and counts["shadow"] > 15
            and counts["outline"] > 20
        )
        if locked_exit:
            return "exit_locked_key", min(1.0, exit_score * 4)
        if conditional_exit:
            return "exit_conditional", min(1.0, exit_score * 4)
        if normal_exit:
            return "exit_normal", min(1.0, exit_score * 4)

    if floor_score > 0.25:
        return "floor", min(1.0, floor_score * 3)

    return "floor", 0.0


def is_chest_label(label: TileLabel) -> bool:
    return label in {"chest_key", "chest_gold", "chest_heal", "chest_item"}


def is_exit_label(label: TileLabel) -> bool:
    return label in {"exit_normal", "exit_locked_key", "exit_conditional"}


def classify_chest_type(tile: np.ndarray) -> TileLabel:
    coin = count_near_color(tile, PALETTE["coin"], tolerance=12)
    heart = count_near_color(tile, PALETTE["heart"], tolerance=12)
    if coin >= 8 and coin >= heart:
        return "chest_gold"
    if heart >= 8:
        return "chest_heal"

    # Key icons add yellow pixels beyond the normal chest band at the far
    # right edge. Item chests currently render without a separate loot icon.
    key_extension = count_near_color(tile[5:6, 14:16], PALETTE["chest_band"], tolerance=12)
    if key_extension >= 2:
        return "chest_key"
    return "chest_item"


def count_near_color(tile: np.ndarray, color: tuple[int, int, int], *, tolerance: int) -> int:
    return int(color_mask(tile, color, tolerance=tolerance).sum())


def is_open_chest_tile(tile: np.ndarray) -> bool:
    wood = count_near_color(tile, PALETTE["chest_wood"], tolerance=14)
    top_band = count_near_color(tile[1:4], PALETTE["chest_band"], tolerance=14)
    closed_band = count_near_color(tile[4:7], PALETTE["chest_band"], tolerance=14)
    inner = count_near_color(tile[2:7], PALETTE["chest_inner"], tolerance=14)
    return wood > 25 and top_band >= 12 and closed_band <= 18 and inner >= 12


def color_mask(image: np.ndarray, color: tuple[int, int, int], *, tolerance: int) -> np.ndarray:
    target = np.asarray(color, dtype=np.int16)
    diff = np.abs(image.astype(np.int16) - target)
    return np.all(diff <= tolerance, axis=-1)


def is_boundary_tile(pos: Position) -> bool:
    x, y = pos
    return (
        x == 0
        or x == ROOM_WIDTH_TILES - 1
        or y == 0
        or y == ROOM_HEIGHT_TILES - 1
    )


def clamp_tile(pos: Position) -> Position:
    x, y = pos
    return (
        min(max(x, 0), ROOM_WIDTH_TILES - 1),
        min(max(y, 0), ROOM_HEIGHT_TILES - 1),
    )
