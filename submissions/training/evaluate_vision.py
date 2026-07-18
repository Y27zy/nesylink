from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from submissions.training.generate_dataset import render_dynamic_sample, render_static_sample
from submissions.vision_dynamic_resnet import (
    DYNAMIC_INDEX_TO_CLASS,
    FACING_NAMES,
    OUTPUT_STRIDE,
    CenterNetDetector,
)
from submissions.vision_preprocess import COLOR_VARIANTS, apply_color_variant
from submissions.vision_static_resnet import (
    CHEST_NAMES,
    EXIT_NAMES,
    OBJECT_NAMES,
    STATE_NAMES,
    TERRAIN_NAMES,
    BatchedStaticClassifier,
)


def evaluate_static(samples: int, seed: int) -> None:
    classifier = BatchedStaticClassifier()
    print(f"static backend={classifier.backend}")
    for variant_index, variant in enumerate(COLOR_VARIANTS):
        correct: defaultdict[str, int] = defaultdict(int)
        total: defaultdict[str, int] = defaultdict(int)
        images: list[np.ndarray] = []
        targets = []
        for index in range(samples):
            rng = np.random.default_rng(seed + variant_index * 100003 + index)
            from submissions.training.generate_dataset import STATIC_SYMBOLS

            symbol = STATIC_SYMBOLS[index % len(STATIC_SYMBOLS)]
            image, target = render_static_sample(rng, symbol)
            images.append(apply_color_variant(image, variant))
            targets.append(target)
        probabilities = classifier.classify_batch(np.stack(images))
        for index, target in enumerate(targets):
            expected = {
                "terrain": target.terrain,
                "object": target.object,
                "chest": target.chest,
                "exit": target.exit,
                "state": target.state,
            }
            relevant = {
                "terrain": True,
                "object": True,
                "chest": OBJECT_NAMES[target.object] == "chest",
                "exit": OBJECT_NAMES[target.object] == "exit",
                "state": target.state_relevant,
            }
            for head in expected:
                if not relevant[head]:
                    continue
                total[head] += 1
                correct[head] += int(int(probabilities[head][index].argmax()) == expected[head])
        metrics = " ".join(
            f"{head}={correct[head] / max(total[head], 1):.3f}"
            for head in ("terrain", "object", "chest", "exit", "state")
        )
        print(f"  {variant:13s} {metrics}")


def evaluate_dynamic(samples: int, seed: int) -> None:
    detector = CenterNetDetector()
    print(f"dynamic backend={detector.backend} threshold={detector.threshold:.2f}")
    for variant_index, variant in enumerate(COLOR_VARIANTS):
        true_positive = 0
        false_positive = 0
        false_negative = 0
        player_hits = 0
        facing_hits = 0
        center_errors: list[float] = []
        for index in range(samples):
            rng = np.random.default_rng(seed + variant_index * 100003 + index)
            image, targets = render_dynamic_sample(rng)
            prediction = detector.detect(apply_color_variant(image, variant))
            expected: list[tuple[str, tuple[int, int]]] = []
            for class_index, label in DYNAMIC_INDEX_TO_CLASS.items():
                ys, xs = np.where(targets["heatmap"][class_index] == 1.0)
                expected.extend(
                    (label, (int(x * OUTPUT_STRIDE), int(y * OUTPUT_STRIDE)))
                    for y, x in zip(ys, xs)
                )
            unmatched = list(prediction.objects)
            for label, center in expected:
                candidates = [obj for obj in unmatched if obj.kind == label]
                match = min(
                    candidates,
                    key=lambda obj: abs(obj.center_px[0] - center[0]) + abs(obj.center_px[1] - center[1]),
                    default=None,
                )
                error = (
                    abs(match.center_px[0] - center[0]) + abs(match.center_px[1] - center[1])
                    if match is not None
                    else 999
                )
                if match is not None and error <= 8:
                    true_positive += 1
                    center_errors.append(float(error))
                    unmatched.remove(match)
                    if label == "player":
                        player_hits += 1
                        gy, gx = np.argwhere(targets["facing"] >= 0)[0]
                        expected_facing = FACING_NAMES[int(targets["facing"][gy, gx])]
                        facing_hits += int(prediction.player_facing == expected_facing)
                else:
                    false_negative += 1
            false_positive += len(unmatched)
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        mean_error = float(np.mean(center_errors)) if center_errors else float("nan")
        print(
            f"  {variant:13s} precision={precision:.3f} recall={recall:.3f} "
            f"player={player_hits / samples:.3f} facing={facing_hits / max(player_hits, 1):.3f} "
            f"center_l1={mean_error:.2f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-samples", type=int, default=460)
    parser.add_argument("--dynamic-samples", type=int, default=120)
    parser.add_argument("--seed", type=int, default=912731)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    evaluate_static(args.static_samples, args.seed)
    evaluate_dynamic(args.dynamic_samples, args.seed + 1)
