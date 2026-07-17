"""Capture reproducible policy screenshots at important task milestones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pygame

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nesylink.env import make_env
from utils.evaluate_policy import (
    apply_obs_variant,
    build_policy_info,
    call_policy,
    event_names,
    is_success,
    load_policy,
    materialize_spatial_map_variant,
    reset_policy,
)


DEFAULT_MILESTONES = (
    "monster_killed",
    "key_collected",
    "chest_opened",
    "door_opened",
    "world_completed",
)


def save_frame(frame: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.asarray(frame, dtype=np.uint8)
    surface = pygame.surfarray.make_surface(np.transpose(pixels, (1, 0, 2)))
    pygame.image.save(surface, str(path))


def capture(args: argparse.Namespace) -> None:
    policy = load_policy(args.policy)
    env_kwargs = {
        "observation_mode": "pixels",
        "render_mode": "rgb_array",
    }
    if args.max_steps is not None:
        env_kwargs["max_steps"] = args.max_steps

    if args.map_variant == "default":
        env = make_env(task_id=args.task, **env_kwargs)
    else:
        map_path = materialize_spatial_map_variant(
            args.task,
            args.map_variant,
            seed=args.seed,
        )
        env = make_env(task_id=args.task, map_path=map_path, **env_kwargs)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reset_policy(policy)
    raw_obs, raw_info = env.reset(seed=args.seed)
    obs = apply_obs_variant(raw_obs, args.obs_variant, info=raw_info, env=env)
    policy_info = build_policy_info(
        info_mode="safe",
        raw_info=raw_info,
        last_reward=0.0,
        task_id=args.task,
    )

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    total_reward = 0.0
    terminated = False
    truncated = False
    step = 0

    start_path = output_dir / "00_start.png"
    save_frame(env.render(), start_path)
    records.append({"milestone": "start", "step": 0, "path": start_path.name})

    try:
        while not (terminated or truncated):
            action = call_policy(policy, obs, policy_info)
            raw_obs, reward, terminated, truncated, raw_info = env.step(action)
            step += 1
            total_reward += float(reward)
            obs = apply_obs_variant(
                raw_obs,
                args.obs_variant,
                info=raw_info,
                env=env,
            )
            policy_info = build_policy_info(
                info_mode="safe",
                raw_info=raw_info,
                last_reward=float(reward),
                task_id=args.task,
            )

            for event in event_names(raw_info):
                if event not in args.milestones or event in seen:
                    continue
                seen.add(event)
                path = output_dir / f"{len(records):02d}_{event}.png"
                save_frame(env.render(), path)
                records.append(
                    {"milestone": event, "step": step, "path": path.name}
                )
    finally:
        env.close()

    manifest = {
        "task_id": args.task,
        "policy": args.policy,
        "seed": args.seed,
        "map_variant": args.map_variant,
        "obs_variant": args.obs_variant,
        "steps": step,
        "total_reward": total_reward,
        "success": is_success(raw_info, terminated),
        "terminal_reason": raw_info.get("terminal_reason"),
        "screenshots": records,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--task", default="mathematical_logic/task_3")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--map-variant",
        choices=("default", "spatial_a", "spatial_b", "spatial_c"),
        default="default",
    )
    parser.add_argument("--obs-variant", default="default")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--output-dir", default="results/d/task3_evidence")
    parser.add_argument(
        "--milestones",
        nargs="+",
        default=list(DEFAULT_MILESTONES),
    )
    return parser.parse_args()


if __name__ == "__main__":
    capture(parse_args())
