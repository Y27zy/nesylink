from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.nn.functional as functional
from torch import nn

from submissions.training.generate_dataset import generate_dynamic_batch
from submissions.vision_dynamic_resnet import DEFAULT_WEIGHTS_PATH, DynamicCenterNet


def centernet_focal_loss(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    probabilities = torch.sigmoid(logits).clamp(1e-4, 1.0 - 1e-4)
    positives = targets.eq(1.0)
    negatives = targets.lt(1.0)
    negative_weights = (1.0 - targets).pow(4)
    positive_loss = -(probabilities.log()) * (1.0 - probabilities).pow(2) * positives
    negative_loss = -((1.0 - probabilities).log()) * probabilities.pow(2) * negative_weights * negatives
    count = positives.sum().clamp(min=1)
    return (positive_loss.sum() + negative_loss.sum()) / count


def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = DynamicCenterNet(nn).to(device)
    if args.resume and Path(args.resume).exists():
        payload = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(payload.get("model_state_dict", payload))
        print(f"resumed {args.resume}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    model.train()
    for step in range(args.steps):
        features, targets_np = generate_dynamic_batch(args.batch_size, args.seed + step * args.batch_size)
        inputs = torch.from_numpy(features).to(device)
        targets = {
            key: torch.from_numpy(value).to(device) for key, value in targets_np.items()
        }
        output = model(inputs)
        heatmap_loss = centernet_focal_loss(output["heatmap"], targets["heatmap"])
        offset_mask = targets["offset_mask"].expand_as(output["offset"])
        offset_loss = functional.smooth_l1_loss(
            output["offset"] * offset_mask,
            targets["offset"] * offset_mask,
            reduction="sum",
        ) / offset_mask.sum().clamp(min=1)
        facing_mask = targets["facing"] >= 0
        facing_logits = output["facing"].permute(0, 2, 3, 1)[facing_mask]
        facing_loss = functional.cross_entropy(facing_logits, targets["facing"][facing_mask])
        loss = heatmap_loss + 2.0 * offset_loss + 0.35 * facing_loss
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % args.log_every == 0:
            print(
                f"step={step + 1}/{args.steps} loss={loss.item():.4f} "
                f"heat={heatmap_loss.item():.4f} offset={offset_loss.item():.4f} device={device}"
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.cpu().state_dict(),
            "model": "dynamic_centernet_v2",
            "threshold": args.threshold,
            "seed": args.seed,
            "steps": args.steps,
        },
        output_path,
    )
    print(f"saved {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--learning-rate", type=float, default=1.5e-3)
    parser.add_argument("--threshold", type=float, default=0.28)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--output", default=str(DEFAULT_WEIGHTS_PATH))
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
