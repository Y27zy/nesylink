from __future__ import annotations

from typing import Literal

import numpy as np


ColorVariant = Literal[
    "default",
    "grayscale",
    "dark",
    "bright",
    "high_contrast",
    "inverted",
]

COLOR_VARIANTS: tuple[ColorVariant, ...] = (
    "default",
    "grayscale",
    "dark",
    "bright",
    "high_contrast",
    "inverted",
)

ROBUST_CHANNELS = 9


def apply_color_variant(image: np.ndarray, variant: ColorVariant) -> np.ndarray:
    """Apply the exact color transformations used by the robustness suite."""

    source = image.astype(np.float32)
    if variant == "grayscale":
        gray = source.mean(axis=-1, keepdims=True)
        source = np.repeat(gray, 3, axis=-1)
    elif variant == "dark":
        source *= 0.55
    elif variant == "bright":
        source *= 1.35
    elif variant == "high_contrast":
        source = np.where(source > 127.0, 255.0, 0.0)
    elif variant == "inverted":
        source = 255.0 - source
    return np.clip(source, 0.0, 255.0).astype(np.uint8)


def robust_channels(images: np.ndarray) -> np.ndarray:
    """Convert RGB images to color-aware and color-stable feature channels.

    Input may be HxWx3 or NxHxWx3. The returned layout is Nx9xHxW.
    Normalization is performed per image so brightness changes do not alter
    scale, while raw RGB and chroma channels preserve useful type colors.
    """

    array = np.asarray(images)
    if array.ndim == 3:
        array = array[None, ...]
    if array.ndim != 4 or array.shape[-1] != 3:
        raise ValueError(f"expected NHWC RGB images, got {array.shape!r}")

    rgb = array.astype(np.float32) / 255.0
    mean = rgb.mean(axis=(1, 2), keepdims=True)
    std = rgb.std(axis=(1, 2), keepdims=True)
    normalized = (rgb - mean) / np.maximum(std, 0.08)

    luminance = (
        rgb[..., 0:1] * 0.299
        + rgb[..., 1:2] * 0.587
        + rgb[..., 2:3] * 0.114
    )
    luma_mean = luminance.mean(axis=(1, 2), keepdims=True)
    luma_std = luminance.std(axis=(1, 2), keepdims=True)
    luminance = (luminance - luma_mean) / np.maximum(luma_std, 0.08)

    gray = rgb.mean(axis=-1)
    dx = np.zeros_like(gray)
    dy = np.zeros_like(gray)
    dx[:, :, 1:-1] = np.abs(gray[:, :, 2:] - gray[:, :, :-2]) * 0.5
    dy[:, 1:-1, :] = np.abs(gray[:, 2:, :] - gray[:, :-2, :]) * 0.5
    edges = np.maximum(dx, dy)

    chroma_rg = (rgb[..., 0] - rgb[..., 1])[..., None]
    chroma_by = (rgb[..., 2] - 0.5 * (rgb[..., 0] + rgb[..., 1]))[..., None]
    features = np.concatenate(
        (
            normalized,
            luminance,
            dx[..., None],
            dy[..., None],
            edges[..., None],
            chroma_rg,
            chroma_by,
        ),
        axis=-1,
    )
    return np.ascontiguousarray(features.transpose(0, 3, 1, 2), dtype=np.float32)


def robust_frame_channels(images: np.ndarray) -> np.ndarray:
    """Canonicalize the suite's full-frame inversion before feature extraction."""

    array = np.asarray(images)
    single = array.ndim == 3
    batch = array[None, ...] if single else array
    if batch.ndim != 4 or batch.shape[-1] != 3:
        raise ValueError(f"expected NHWC RGB frames, got {batch.shape!r}")
    canonical = batch.copy()
    means = canonical.astype(np.float32).mean(axis=(1, 2))
    inverted = (means.mean(axis=1) > 180.0) | (means[:, 0] > means[:, 2] + 20.0)
    canonical[inverted] = 255 - canonical[inverted]
    return robust_channels(canonical)


def extract_tile_batch(
    obs: np.ndarray,
    *,
    tile_size: int = 16,
    width_tiles: int = 10,
    height_tiles: int = 8,
) -> np.ndarray:
    """Return all map tiles as one row-major NHWC batch without Python loops."""

    map_pixels = np.asarray(obs)[: height_tiles * tile_size, : width_tiles * tile_size, :3]
    expected = (height_tiles * tile_size, width_tiles * tile_size, 3)
    if map_pixels.shape != expected:
        raise ValueError(f"expected map pixels {expected!r}, got {map_pixels.shape!r}")
    tiles = map_pixels.reshape(height_tiles, tile_size, width_tiles, tile_size, 3)
    return np.ascontiguousarray(tiles.transpose(0, 2, 1, 3, 4).reshape(-1, tile_size, tile_size, 3))
