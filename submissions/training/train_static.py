from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.nn.functional as functional
from torch import nn

from submissions.training.generate_dataset import generate_static_batch
from submissions.vision_static_resnet import DEFAULT_WEIGHTS_PATH, StaticMultiHeadCNN


def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = StaticMultiHeadCNN(nn).to(device)
    if args.resume and Path(args.resume).exists():
        payload = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(payload.get("model_state_dict", payload))
        print(f"resumed {args.resume}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    model.train()
    for step in range(args.steps):
        features, targets_np = generate_static_batch(args.batch_size, args.seed + step * args.batch_size)
        inputs = torch.from_numpy(features).to(device)
        targets = {
            key: torch.from_numpy(value).to(device) for key, value in targets_np.items()
        }
        output = model(inputs)
        loss = functional.cross_entropy(output["terrain"], targets["terrain"])
        loss = loss + functional.cross_entropy(output["object"], targets["object"])
        chest_mask = targets["object"] == 1
        exit_mask = targets["object"] == 5
        state_mask = targets["state_relevant"]
        if chest_mask.any():
            loss = loss + functional.cross_entropy(output["chest"][chest_mask], targets["chest"][chest_mask])
        if exit_mask.any():
            loss = loss + functional.cross_entropy(output["exit"][exit_mask], targets["exit"][exit_mask])
        if state_mask.any():
            loss = loss + 0.7 * functional.cross_entropy(output["state"][state_mask], targets["state"][state_mask])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        if step == 0 or (step + 1) % args.log_every == 0:
            print(f"step={step + 1}/{args.steps} loss={loss.item():.4f} device={device}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.cpu().state_dict(),
            "model": "static_multitask_v2",
            "seed": args.seed,
            "steps": args.steps,
        },
        output_path,
    )
    print(f"saved {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=900)
    parser.add_argument("--batch-size", type=int, default=192)
    parser.add_argument("--learning-rate", type=float, default=2e-3)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--output", default=str(DEFAULT_WEIGHTS_PATH))
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
