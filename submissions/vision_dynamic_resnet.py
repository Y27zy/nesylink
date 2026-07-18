from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .state import Position
from .vision_preprocess import ROBUST_CHANNELS, robust_frame_channels
from .vision_static_resnet import ROOM_HEIGHT_TILES, ROOM_WIDTH_TILES, TILE_SIZE, color_mask


DynamicLabel = Literal["player", "monster_chaser", "monster_patroller", "monster_ambusher"]

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "models" / "dynamic_centernet.pt"
OUTPUT_STRIDE = 4

DYNAMIC_LABELS: tuple[DynamicLabel, ...] = (
    "player",
    "monster_chaser",
    "monster_patroller",
    "monster_ambusher",
)
DYNAMIC_CLASS_TO_INDEX = {name: index for index, name in enumerate(DYNAMIC_LABELS)}
DYNAMIC_INDEX_TO_CLASS = {index: name for name, index in DYNAMIC_CLASS_TO_INDEX.items()}
FACING_NAMES = ("up", "down", "left", "right")


@dataclass(frozen=True)
class DynamicObject:
    kind: DynamicLabel
    tile: Position
    center_px: tuple[int, int]
    bbox: tuple[int, int, int, int]
    confidence: float


@dataclass(frozen=True)
class DynamicVisionResult:
    player: Position | None
    player_bbox: tuple[int, int, int, int] | None
    player_facing: str | None
    monsters: set[Position]
    objects: list[DynamicObject]
    backend: str


class DynamicCenterNet:
    """Factory for a small fully convolutional multi-instance detector."""

    def __new__(cls, nn: Any):  # noqa: D102
        class SeparableBlock(nn.Module):
            def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Conv2d(
                        in_channels,
                        in_channels,
                        3,
                        stride=stride,
                        padding=1,
                        groups=in_channels,
                        bias=False,
                    ),
                    nn.BatchNorm2d(in_channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(in_channels, out_channels, 1, bias=False),
                    nn.BatchNorm2d(out_channels),
                    nn.ReLU(inplace=True),
                )

            def forward(self, x):  # noqa: ANN001
                return self.layers(x)

        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.features = nn.Sequential(
                    nn.Conv2d(ROBUST_CHANNELS, 20, 3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(20),
                    nn.ReLU(inplace=True),
                    SeparableBlock(20, 32, stride=2),
                    SeparableBlock(32, 48),
                    SeparableBlock(48, 48),
                    nn.Conv2d(48, 64, 3, padding=2, dilation=2, bias=False),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                )
                self.heatmap_head = nn.Sequential(
                    nn.Conv2d(64, 32, 3, padding=1),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(32, len(DYNAMIC_LABELS), 1),
                )
                self.offset_head = nn.Sequential(
                    nn.Conv2d(64, 24, 3, padding=1),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(24, 2, 1),
                )
                self.facing_head = nn.Conv2d(64, len(FACING_NAMES), 1)
                nn.init.constant_(self.heatmap_head[-1].bias, -2.19)

            def forward(self, x):  # noqa: ANN001
                features = self.features(x)
                return {
                    "heatmap": self.heatmap_head(features),
                    "offset": self.offset_head(features),
                    "facing": self.facing_head(features),
                }

        return Model()


class CenterNetDetector:
    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS_PATH) -> None:
        self.weights_path = weights_path
        self.model: Any | None = None
        self.torch: Any | None = None
        self.threshold = 0.32
        self.backend = "components"
        self._load()

    def _load(self) -> None:
        if not self.weights_path.exists():
            return
        try:
            import torch
            from torch import nn

            model = DynamicCenterNet(nn)
            payload = torch.load(self.weights_path, map_location="cpu", weights_only=False)
            model.load_state_dict(payload.get("model_state_dict", payload))
            model.eval()
            self.threshold = float(payload.get("threshold", self.threshold))
            self.model = model
            self.torch = torch
            self.backend = "centernet"
        except (ImportError, OSError, RuntimeError, KeyError, ValueError):
            self.model = None
            self.torch = None
            self.backend = "components"

    def detect(self, obs: np.ndarray) -> DynamicVisionResult:
        if self.model is None or self.torch is None:
            return detect_dynamic_components(obs)
        result = self._detect_model(obs)
        if result.player is None:
            fallback = detect_dynamic_components(obs)
            if fallback.player is not None:
                return replace_dynamic_player(result, fallback)
        return result

    def _detect_model(self, obs: np.ndarray) -> DynamicVisionResult:
        assert self.model is not None and self.torch is not None
        torch = self.torch
        map_pixels = np.asarray(obs)[: ROOM_HEIGHT_TILES * TILE_SIZE, : ROOM_WIDTH_TILES * TILE_SIZE, :3]
        tensor = torch.from_numpy(robust_frame_channels(map_pixels))
        with torch.inference_mode():
            output = self.model(tensor)
            heatmaps = torch.sigmoid(output["heatmap"])[0]
            offsets = output["offset"][0]
            facing_logits = output["facing"][0]
            pooled = torch.nn.functional.max_pool2d(heatmaps[None], 3, stride=1, padding=1)[0]
            peaks = heatmaps * (heatmaps >= pooled)

        objects: list[DynamicObject] = []
        for class_index, label in DYNAMIC_INDEX_TO_CLASS.items():
            class_threshold = 0.05 if label == "player" else self.threshold
            ys, xs = torch.where(peaks[class_index] >= class_threshold)
            candidates: list[tuple[float, int, int]] = []
            for gy, gx in zip(ys.tolist(), xs.tolist()):
                candidates.append((float(peaks[class_index, gy, gx]), gy, gx))
            candidates.sort(reverse=True)
            max_instances = 6 if label == "player" else 8
            accepted: list[tuple[int, int]] = []
            for confidence, gy, gx in candidates:
                offset_x = float(offsets[0, gy, gx].clamp(-0.25, 1.25))
                offset_y = float(offsets[1, gy, gx].clamp(-0.25, 1.25))
                center = (
                    int(round((gx + offset_x) * OUTPUT_STRIDE)),
                    int(round((gy + offset_y) * OUTPUT_STRIDE)),
                )
                if any(abs(center[0] - x) + abs(center[1] - y) < 10 for x, y in accepted):
                    continue
                accepted.append(center)
                objects.append(
                    DynamicObject(
                        kind=label,
                        tile=tile_from_center(center),
                        center_px=center,
                        bbox=bbox_from_center(center),
                        confidence=confidence,
                    )
                )
                if len(accepted) >= max_instances:
                    break

        player_objects = [obj for obj in objects if obj.kind == "player"]
        player_object = max(player_objects, key=lambda obj: obj.confidence, default=None)
        player_facing: str | None = None
        if player_object is not None:
            gx = min(max(player_object.center_px[0] // OUTPUT_STRIDE, 0), facing_logits.shape[2] - 1)
            gy = min(max(player_object.center_px[1] // OUTPUT_STRIDE, 0), facing_logits.shape[1] - 1)
            player_facing = FACING_NAMES[int(facing_logits[:, gy, gx].argmax())]

        monsters = {obj.tile for obj in objects if obj.kind != "player"}
        return DynamicVisionResult(
            player=player_object.tile if player_object else None,
            player_bbox=player_object.bbox if player_object else None,
            player_facing=player_facing,
            monsters=monsters,
            objects=objects,
            backend=self.backend,
        )


_DETECTOR: CenterNetDetector | None = None


def get_dynamic_detector() -> CenterNetDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = CenterNetDetector()
    return _DETECTOR


def reset_dynamic_detector() -> None:
    global _DETECTOR
    _DETECTOR = None


def extract_dynamic_objects(obs: np.ndarray) -> DynamicVisionResult:
    return get_dynamic_detector().detect(obs)


def replace_dynamic_player(
    result: DynamicVisionResult,
    fallback: DynamicVisionResult,
) -> DynamicVisionResult:
    fallback_players = [obj for obj in fallback.objects if obj.kind == "player"]
    non_player_objects = [obj for obj in result.objects if obj.kind != "player"]
    return DynamicVisionResult(
        player=fallback.player,
        player_bbox=fallback.player_bbox,
        player_facing=fallback.player_facing,
        monsters=result.monsters,
        objects=non_player_objects + fallback_players,
        backend=f"{result.backend}+components",
    )


MONSTER_COLORS: dict[DynamicLabel, tuple[int, int, int]] = {
    "monster_chaser": (238, 126, 28),
    "monster_patroller": (200, 78, 16),
    "monster_ambusher": (255, 180, 48),
}
PLAYER_COLORS = ((36, 198, 72), (126, 248, 82))


def detect_dynamic_components(obs: np.ndarray) -> DynamicVisionResult:
    """Default-color fallback for machines that cannot load PyTorch weights."""

    map_pixels = np.asarray(obs)[: ROOM_HEIGHT_TILES * TILE_SIZE, : ROOM_WIDTH_TILES * TILE_SIZE, :3]
    objects: list[DynamicObject] = []
    player_mask = np.zeros(map_pixels.shape[:2], dtype=bool)
    for color in PLAYER_COLORS:
        player_mask |= color_mask(map_pixels, color, tolerance=4)
    player_box = largest_component(dilate_mask(player_mask, 2), min_pixels=18)
    player: Position | None = None
    if player_box is not None:
        center = bbox_center(player_box)
        player = tile_from_center(center)
        objects.append(DynamicObject("player", player, center, player_box, 1.0))

    monsters: set[Position] = set()
    for label, color in MONSTER_COLORS.items():
        mask = dilate_mask(color_mask(map_pixels, color, tolerance=20), 1)
        for bbox in connected_components(mask, min_pixels=12):
            center = bbox_center(bbox)
            tile = tile_from_center(center)
            if tile == player:
                continue
            monsters.add(tile)
            objects.append(DynamicObject(label, tile, center, bbox, 1.0))
    return DynamicVisionResult(
        player=player,
        player_bbox=player_box,
        player_facing=None,
        monsters=monsters,
        objects=objects,
        backend="components",
    )


def connected_components(mask: np.ndarray, *, min_pixels: int) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: list[tuple[int, int, int, int]] = []
    for seed_y, seed_x in zip(*np.nonzero(mask)):
        if visited[seed_y, seed_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(int(seed_x), int(seed_y))])
        visited[seed_y, seed_x] = True
        xs: list[int] = []
        ys: list[int] = []
        while queue:
            x, y = queue.popleft()
            xs.append(x)
            ys.append(y)
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))
        if len(xs) >= min_pixels:
            boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return boxes


def largest_component(mask: np.ndarray, *, min_pixels: int) -> tuple[int, int, int, int] | None:
    boxes = connected_components(mask, min_pixels=min_pixels)
    return max(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), default=None)


def dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    height, width = mask.shape
    padded = np.pad(mask, radius)
    output = np.zeros_like(mask)
    for dy in range(radius * 2 + 1):
        for dx in range(radius * 2 + 1):
            output |= padded[dy : dy + height, dx : dx + width]
    return output


def bbox_center(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bbox
    return ((left + right) // 2, (top + bottom) // 2)


def bbox_from_center(center: tuple[int, int], size: int = TILE_SIZE) -> tuple[int, int, int, int]:
    half = size // 2
    return (center[0] - half, center[1] - half, center[0] + half, center[1] + half)


def tile_from_center(center: tuple[int, int]) -> Position:
    return (
        min(max(center[0] // TILE_SIZE, 0), ROOM_WIDTH_TILES - 1),
        min(max(center[1] // TILE_SIZE, 0), ROOM_HEIGHT_TILES - 1),
    )
