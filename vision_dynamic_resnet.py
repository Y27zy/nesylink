from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from state import Position
from vision_static_resnet import ROOM_HEIGHT_TILES, ROOM_WIDTH_TILES, TILE_SIZE, color_mask


DynamicLabel = Literal["player", "monster_chaser", "monster_patroller", "monster_ambusher"]

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "models" / "dynamic_pixel_resnet.pt"

DYNAMIC_LABELS: tuple[DynamicLabel, ...] = (
    "player",
    "monster_chaser",
    "monster_patroller",
    "monster_ambusher",
)

DYNAMIC_CLASS_TO_INDEX = {label: index for index, label in enumerate(DYNAMIC_LABELS)}
DYNAMIC_INDEX_TO_CLASS = {index: label for label, index in DYNAMIC_CLASS_TO_INDEX.items()}

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
    monsters: set[Position]
    objects: list[DynamicObject]
    backend: str


class OptionalResNetDynamicDetector:
    """Full-frame dynamic detector.

    The ResNet variant predicts C x 8 x 10 heatmaps from the full
    3 x 128 x 160 observation. Without weights, color connected components are
    used as a deterministic fallback.
    """

    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS_PATH) -> None:
        self.weights_path = weights_path
        self.model: Any | None = None
        self.torch: Any | None = None
        self.backend = "components"
        self._try_load_resnet()

    def detect(self, obs: np.ndarray) -> DynamicVisionResult:
        if self.model is not None and self.torch is not None:
            return self._detect_with_resnet(obs)
        return detect_dynamic_components(obs)

    def _try_load_resnet(self) -> None:
        if not self.weights_path.exists():
            return
        try:
            import torch
            from torch import nn
        except Exception:
            return

        model = PixelHeatmapUNet(num_classes=len(DYNAMIC_LABELS), nn=nn)
        payload = torch.load(self.weights_path, map_location="cpu")
        state_dict = payload.get("model_state_dict", payload) if isinstance(payload, dict) else payload
        model.load_state_dict(state_dict)
        model.eval()
        self.model = model
        self.torch = torch
        self.backend = "resnet"

    def _detect_with_resnet(self, obs: np.ndarray) -> DynamicVisionResult:
        assert self.model is not None
        assert self.torch is not None

        H, W = obs.shape[:2]  # 128, 160

        tensor = self.torch.from_numpy(obs.astype(np.float32) / 255.0)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)
        with self.torch.no_grad():
            heatmaps = self.model(tensor)[0]  # (C, 128, 160)，模型已含 sigmoid

        objects: list[DynamicObject] = []
        player: Position | None = None
        player_bbox: tuple[int, int, int, int] | None = None
        monsters: set[Position] = set()

        for class_index, label in DYNAMIC_INDEX_TO_CLASS.items():
            hm = heatmaps[class_index]  # (128, 160)
            flat_index = int(self.torch.argmax(hm).item())
            confidence = float(hm.flatten()[flat_index].item())
            if confidence < 0.45:
                continue

            # 像素级坐标（直接从 argmax 得到）
            y = flat_index // W
            x = flat_index % W
            center_px = (x, y)
            # 反算 tile 坐标（兼容现有 vision.py 接口）
            tile = (x // TILE_SIZE, y // TILE_SIZE)
            bbox = bbox_from_center(center_px, size=TILE_SIZE)

            obj = DynamicObject(label, tile, center_px, bbox, confidence)
            objects.append(obj)
            if label == "player":
                player = tile
                player_bbox = bbox
            else:
                monsters.add(tile)

        return DynamicVisionResult(
            player=player,
            player_bbox=player_bbox,
            monsters=monsters,
            objects=objects,
            backend=self.backend,
        )



class PixelHeatmapUNet:

    """Pixel-level encoder-decoder for C×128×160 heatmap regression."""

    def __new__(cls, num_classes: int, nn: Any):
        class ResBlock(nn.Module):
            def __init__(self, channels: int):
                super().__init__()
                self.block = nn.Sequential(
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                    nn.BatchNorm2d(channels),
                )
                self.relu = nn.ReLU(inplace=True)

            def forward(self, x):
                return self.relu(x + self.block(x))

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                # Encoder
                self.enc1 = nn.Sequential(
                    nn.Conv2d(3, 32, 3, padding=1, bias=False),
                    nn.BatchNorm2d(32), nn.ReLU(inplace=True),
                )
                self.enc_res1 = ResBlock(32)
                self.enc_down1 = nn.Sequential(
                    nn.Conv2d(32, 64, 3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(64), nn.ReLU(inplace=True),
                )
                self.enc_res2 = ResBlock(64)
                self.enc_down2 = nn.Sequential(
                    nn.Conv2d(64, 96, 3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(96), nn.ReLU(inplace=True),
                )
                self.enc_res3 = ResBlock(96)
                # Bottleneck
                self.bottleneck = nn.Sequential(
                    nn.Conv2d(96, 128, 3, padding=1, bias=False),
                    nn.BatchNorm2d(128), nn.ReLU(inplace=True),
                    ResBlock(128),
                )
                # Decoder
                self.dec_up1 = nn.Sequential(
                    nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
                    nn.Conv2d(128, 64, 3, padding=1, bias=False),
                    nn.BatchNorm2d(64), nn.ReLU(inplace=True),
                )
                self.dec_res1 = ResBlock(64)
                self.dec_up2 = nn.Sequential(
                    nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
                    nn.Conv2d(64, 32, 3, padding=1, bias=False),
                    nn.BatchNorm2d(32), nn.ReLU(inplace=True),
                )
                self.dec_res2 = ResBlock(32)
                self.head = nn.Conv2d(32, num_classes, 3, padding=1)
                self.sigmoid = nn.Sigmoid()

            def forward(self, x):
                e1 = self.enc_res1(self.enc1(x))
                e2 = self.enc_res2(self.enc_down1(e1))
                e3 = self.enc_res3(self.enc_down2(e2))
                b = self.bottleneck(e3)
                d1 = self.dec_res1(self.dec_up1(b))
                d2 = self.dec_res2(self.dec_up2(d1))
                return self.sigmoid(self.head(d2))

        return Model()

_DETECTOR: OptionalResNetDynamicDetector | None = None


def get_dynamic_detector() -> OptionalResNetDynamicDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = OptionalResNetDynamicDetector()
    return _DETECTOR


def extract_dynamic_objects(obs: np.ndarray) -> DynamicVisionResult:
    return get_dynamic_detector().detect(obs)


def detect_dynamic_components(obs: np.ndarray) -> DynamicVisionResult:
    objects: list[DynamicObject] = []

    player_mask = np.zeros(obs.shape[:2], dtype=bool)
    for color in PLAYER_COLORS[:2]:
        player_mask |= color_mask(obs, color, tolerance=14)

    # The dark outline splits the tunic into several green islands. Join those
    # islands so the component center follows the full moving sprite.
    player_component = largest_component(
        dilate_mask(player_mask, radius=2),
        min_pixels=18,
    )
    player: Position | None = None
    player_bbox: tuple[int, int, int, int] | None = None
    if player_component is not None:
        player_bbox = player_component
        center = player_center_from_component(obs, player_bbox)
        player = tile_from_center(center)
        objects.append(
            DynamicObject(
                kind="player",
                tile=player,
                center_px=center,
                bbox=player_bbox,
                confidence=1.0,
            )
        )

    monsters: set[Position] = set()
    for kind, body_color in MONSTER_COLORS.items():
        monster_mask = color_mask(obs, body_color, tolerance=18)
        for bbox in connected_components(
            dilate_mask(monster_mask, radius=1),
            min_pixels=12,
        ):
            center = bbox_center(bbox)
            tile = monster_tile_from_body_center(kind, center)
            # Avoid treating player detail colors as monster components.
            if player is not None and manhattan(tile, player) <= 0:
                continue
            monsters.add(tile)
            objects.append(
                DynamicObject(
                    kind=kind,
                    tile=tile,
                    center_px=center,
                    bbox=bbox,
                    confidence=1.0,
                )
            )

    return DynamicVisionResult(
        player=player,
        player_bbox=player_bbox,
        monsters=monsters,
        objects=objects,
        backend="components",
    )



##废弃部分
MONSTER_COLORS: dict[DynamicLabel, tuple[int, int, int]] = {
    "monster_chaser": (238, 126, 28),
    "monster_patroller": (200, 78, 16),
    "monster_ambusher": (255, 180, 48),
}
PLAYER_COLORS = (
    (36, 198, 72),
    (126, 248, 82),
    (240, 154, 52),
    (86, 42, 18),
)

MONSTER_CENTER_OFFSETS: dict[DynamicLabel, tuple[int, int]] = {
    # Monster body colors occupy the upper part of each 16x16 sprite.
    "monster_chaser": (0, 2),
    "monster_patroller": (1, 2),
    "monster_ambusher": (1, 2),
    "player": (0, 0),
}


class TinyFullFrameResNet:
    """Tiny ResNet heatmap model without importing torch at module import time."""

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
                self.net = nn.Sequential(
                    nn.Conv2d(3, 32, kernel_size=3, stride=1, padding=1, bias=False),
                    nn.BatchNorm2d(32),
                    nn.ReLU(inplace=True),
                    ResidualBlock(32),
                    nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                    ResidualBlock(64),
                    nn.Conv2d(64, 96, kernel_size=3, stride=2, padding=1, bias=False),
                    nn.BatchNorm2d(96),
                    nn.ReLU(inplace=True),
                    ResidualBlock(96),
                    nn.AdaptiveAvgPool2d((ROOM_HEIGHT_TILES, ROOM_WIDTH_TILES)),
                    nn.Conv2d(96, num_classes, kernel_size=1),
                )

            def forward(self, x):  # noqa: ANN001
                return self.net(x)

        return Model()


def connected_components(mask: np.ndarray, *, min_pixels: int) -> list[tuple[int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: list[tuple[int, int, int, int]] = []

    seed_ys, seed_xs = np.nonzero(mask)
    for seed_y, seed_x in zip(seed_ys.tolist(), seed_xs.tolist()):
        if visited[seed_y, seed_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(seed_x, seed_y)])
        visited[seed_y, seed_x] = True
        component_xs: list[int] = []
        component_ys: list[int] = []

        while queue:
            cx, cy = queue.popleft()
            component_xs.append(cx)
            component_ys.append(cy)
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                if visited[ny, nx] or not mask[ny, nx]:
                    continue
                visited[ny, nx] = True
                queue.append((nx, ny))

        if len(component_xs) >= min_pixels:
            boxes.append(
                (
                    min(component_xs),
                    min(component_ys),
                    max(component_xs) + 1,
                    max(component_ys) + 1,
                )
            )

    return boxes


def largest_component(mask: np.ndarray, *, min_pixels: int) -> tuple[int, int, int, int] | None:
    boxes = connected_components(mask, min_pixels=min_pixels)
    if not boxes:
        return None
    return max(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))


def bbox_center(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bbox
    return ((left + right) // 2, (top + bottom) // 2)


def bbox_from_center(center: tuple[int, int], size: int = TILE_SIZE) -> tuple[int, int, int, int]:
    x, y = center
    half = size // 2
    return (x - half, y - half, x + half, y + half)


def dilate_mask(mask: np.ndarray, *, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    height, width = mask.shape
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    dilated = np.zeros_like(mask, dtype=bool)
    diameter = radius * 2 + 1
    for dy in range(diameter):
        for dx in range(diameter):
            dilated |= padded[dy : dy + height, dx : dx + width]
    return dilated


def monster_tile_from_body_center(kind: DynamicLabel, center: tuple[int, int]) -> Position:
    offset_x, offset_y = MONSTER_CENTER_OFFSETS.get(kind, (0, 0))
    return tile_from_center((center[0] + offset_x, center[1] + offset_y))


def player_center_from_component(
    obs: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> tuple[int, int]:
    center_x, center_y = bbox_center(bbox)
    left, top, right, bottom = bbox

    # Green body pixels are centered one pixel above the entity center. A
    # raised front shield covers the lower tunic, shortening the component by
    # several pixels, so compensate for that recognizable shape as well.
    center_y += 2 if bottom - top <= 12 else 1

    # Left/right sprites have equally narrow green boxes. A single hair pixel
    # identifies the right-facing sprite, whose body center is one pixel left
    # of the entity center.
    if right - left <= 11:
        hair_mask = color_mask(obs, PLAYER_COLORS[3], tolerance=14)
        y0 = max(0, top - 3)
        y1 = min(obs.shape[0], bottom + 3)
        x0 = max(0, left - 3)
        x1 = min(obs.shape[1], right + 3)
        local_y, local_x = np.nonzero(hair_mask[y0:y1, x0:x1])
        if local_x.size and float(local_x.mean() + x0) > center_x:
            center_x += 1

    return center_x, center_y


def tile_center_px(pos: Position) -> tuple[int, int]:
    x, y = pos
    return (x * TILE_SIZE + TILE_SIZE // 2, y * TILE_SIZE + TILE_SIZE // 2)


def tile_from_center(center: tuple[int, int]) -> Position:
    x, y = center
    return (
        min(max(x // TILE_SIZE, 0), ROOM_WIDTH_TILES - 1),
        min(max(y // TILE_SIZE, 0), ROOM_HEIGHT_TILES - 1),
    )


def manhattan(a: Position, b: Position) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
