"""Real-time policy visualization with Pygame.

Run a trained policy step-by-step and watch its behaviour in a graphical
window.  Press **Space** to pause/resume and **Esc** to quit.

Usage::

    python utils/visualize_policy.py --policy agent.py --task mathematical_logic/task_1
    python utils/visualize_policy.py --policy agent.py --task mathematical_logic/task_3 --seed 42 --fps 15

Requirements:  pygame  (already used by ``human_play.py``)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pygame

# ── project root on sys.path ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nesylink.core.constants import (
    ACTION_LABELS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TARGET_FPS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from nesylink.env import make_env
from nesylink.tasks import list_tasks
from utils.evaluate_policy import load_policy, reset_policy, call_policy


# ── colour palette ──────────────────────────────────────────────────────────
COLOR_BG         = (24, 24, 32)
COLOR_OVERLAY_BG = (0, 0, 0, 180)
COLOR_TEXT       = (220, 220, 240)
COLOR_ACCENT     = (72, 198, 108)
COLOR_WARN       = (238, 126, 60)
COLOR_DIM        = (128, 128, 144)

FONT_SIZE_SMALL  = 16
FONT_SIZE_NORMAL = 20

_OVERLAY_MARGIN = 8
_OVERLAY_PAD    = 6


# ── helpers ─────────────────────────────────────────────────────────────────

def _blit_text(
    surface: pygame.Surface,
    lines: list[tuple[str, tuple[int, int, int]]],
    *,
    pos: tuple[int, int] = (10, 10),
    font_size: int = FONT_SIZE_NORMAL,
) -> None:
    """Draw coloured text lines at *pos*, top-to-bottom."""
    font = pygame.font.SysFont("Consolas", font_size)
    x, y = pos
    for text, colour in lines:
        rendered = font.render(text, True, colour)
        surface.blit(rendered, (x, y))
        y += rendered.get_height() + 2


def _draw_status_overlay(
    surface: pygame.Surface,
    *,
    task_id: str,
    step: int,
    total_reward: float,
    action: int | None,
    paused: bool,
    terminal_reason: str | None,
    events: list[str],
) -> None:
    """Semi-transparent info bar at the bottom of the window."""

    # ── event strings (last 3) ─────────────────────────────────────────
    recent_events = events[-3:] if events else []
    event_strs = [f"  + {e}" for e in recent_events]

    lines: list[tuple[str, tuple[int, int, int]]] = [
        (f"Task: {task_id}   Step: {step}   Reward: {total_reward:+.1f}", COLOR_ACCENT),
    ]

    action_label = ACTION_LABELS.get(action, "??") if action is not None else "—"
    lines.append((f"Action: {action_label} (id={action})", COLOR_TEXT))

    if event_strs:
        for es in event_strs:
            lines.append((es, COLOR_WARN))

    if terminal_reason:
        lines.append((
            f"TERMINAL: {terminal_reason}",
            COLOR_WARN,
        ))
    if paused:
        lines.append(("⏸  PAUSED — press SPACE to resume", COLOR_ACCENT))

    # measure total height
    font = pygame.font.SysFont("Consolas", FONT_SIZE_SMALL)
    line_h = font.get_height() + 2
    total_h = len(lines) * line_h + _OVERLAY_PAD * 2

    # draw background rect
    overlay_rect = pygame.Rect(
        _OVERLAY_MARGIN,
        WINDOW_HEIGHT - total_h - _OVERLAY_MARGIN,
        WINDOW_WIDTH - _OVERLAY_MARGIN * 2,
        total_h,
    )
    overlay_surf = pygame.Surface(overlay_rect.size, pygame.SRCALPHA)
    overlay_surf.fill(COLOR_OVERLAY_BG)
    surface.blit(overlay_surf, overlay_rect.topleft)

    _blit_text(
        surface,
        lines,
        pos=(overlay_rect.x + _OVERLAY_PAD, overlay_rect.y + _OVERLAY_PAD),
        font_size=FONT_SIZE_SMALL,
    )


# ── main loop ───────────────────────────────────────────────────────────────

def run_visual(
    *,
    policy: Any,
    task_id: str,
    seed: int,
    max_steps: int | None,
    fps: int,
) -> None:
    """Open a Pygame window and replay *policy* on *task_id* in real-time."""

    env = make_env(
        task_id=task_id,
        observation_mode="pixels",
        render_mode="rgb_array",
        max_steps=max_steps,
    )
    reset_policy(policy, seed=seed, task_id=task_id)

    # ── pygame init ────────────────────────────────────────────────────
    pygame.init()
    pygame.display.set_caption(f"NesyLink Policy Viewer — {task_id}")
    display = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    # ── episode state ──────────────────────────────────────────────────
    obs, info = env.reset(seed=seed)
    step = 0
    total_reward = 0.0
    terminated = False
    truncated = False
    terminal_reason: str | None = None
    events_log: list[str] = []
    last_action: int | None = None

    running = True
    paused = False
    done = False

    print(f"[Viewer]  Task: {task_id}   Seed: {seed}")
    print(f"[Viewer]  SPACE=pause/resume   ESC=quit   R=restart")

    while running:
        # ── handle input ───────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    # restart episode
                    obs, info = env.reset(seed=seed)
                    reset_policy(policy, seed=seed, task_id=task_id)
                    step = 0
                    total_reward = 0.0
                    terminated = False
                    truncated = False
                    terminal_reason = None
                    events_log.clear()
                    last_action = None
                    done = False
                    paused = False
                    print(f"[Viewer]  Episode restarted (seed={seed})")

        if not running:
            break

        # ── step the environment ───────────────────────────────────────
        if not paused and not done:
            try:
                action = call_policy(policy, obs, info)
            except Exception:
                action = 0

            if not env.action_space.contains(action):
                action = 0

            last_action = action
            obs, reward, terminated, truncated, info = env.step(action)
            step += 1
            total_reward += float(reward)

            # collect new events
            for record in info.get("events", {}).get("records", []):
                name = record.get("name") if isinstance(record, dict) else None
                if name:
                    events_log.append(str(name))

            if terminated or truncated:
                done = True
                terminal_reason = info.get("terminal_reason", None)
                result = "✅ SUCCESS" if info.get("game", {}).get("world_completed") or terminal_reason == "world_completed" else "❌ FAIL"
                print(f"[Viewer]  Episode ended: {result} — {terminal_reason or 'truncated'}  "
                      f"steps={step}  reward={total_reward:.2f}")

        # ── render ─────────────────────────────────────────────────────
        frame = env.render()  # full internal frame (SCREEN_W × SCREEN_H)
        surface = pygame.surfarray.make_surface(np.transpose(frame, (1, 0, 2)))
        scaled = pygame.transform.scale(surface, (WINDOW_WIDTH, WINDOW_HEIGHT))
        display.blit(scaled, (0, 0))

        # ── overlay ────────────────────────────────────────────────────
        _draw_status_overlay(
            display,
            task_id=task_id,
            step=step,
            total_reward=total_reward,
            action=last_action,
            paused=paused,
            terminal_reason=terminal_reason if done else None,
            events=events_log,
        )

        pygame.display.flip()
        clock.tick(fps)

    env.close()
    pygame.quit()


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    task_ids = [t.task_id for t in list_tasks()]
    parser = argparse.ArgumentParser(
        description="Visualise a NesyLink policy in a Pygame window.",
    )
    parser.add_argument(
        "--policy",
        required=True,
        help="Policy module or file (e.g. agent.py or agent.py:make_policy).",
    )
    parser.add_argument(
        "--task",
        default="mathematical_logic/task_1",
        choices=task_ids,
        help="Task ID to evaluate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Environment seed.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override maximum episode steps.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=10,
        help="Playback speed in frames per second (default: 10).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy = load_policy(args.policy)
    run_visual(
        policy=policy,
        task_id=args.task,
        seed=args.seed,
        max_steps=args.max_steps,
        fps=args.fps,
    )


if __name__ == "__main__":
    main()
