"""Offline pixel-vision evaluation against NesyLink runtime truth.

This utility may inspect hidden engine state because it is only a development
and reporting tool. Submitted policies must continue to infer state from pixels.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nesylink.core.constants import MAP_PIXEL_HEIGHT, MAP_PIXEL_WIDTH
from nesylink.core.state import tile_to_top_left_px
from nesylink.env import make_env
from state import Position
from vision_dynamic_resnet import extract_dynamic_objects
from vision_interactive import extract_interactive_tiles
from vision_static_resnet import extract_static_tiles


DEFAULT_TASKS = tuple(f"mathematical_logic/task_{index}" for index in range(1, 6))


@dataclass
class SetScore:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    def update(self, predicted: set[Position], expected: set[Position]) -> None:
        self.true_positive += len(predicted & expected)
        self.false_positive += len(predicted - expected)
        self.false_negative += len(expected - predicted)

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 1.0


def visible_exit_tiles(room, player_tile: Position) -> set[Position]:
    visible = {pos for exit_config in room.exits for pos in exit_config.tiles}
    visible -= room.walls

    for trap in room.traps.values():
        if trap.is_active and room.dynamic_tiles.get(trap.pos) != "bridge":
            visible.discard(trap.pos)
    for chest in room.chests.values():
        if chest.is_visible:
            visible.discard(chest.pos)
    for collection in (room.npcs, room.buttons, room.switches, room.monsters):
        for entity in collection.values():
            pos = entity.tile_pos if hasattr(entity, "tile_pos") else entity.pos
            visible.discard(pos)
    visible.discard(player_tile)
    return visible


def room_truth(room, player_tile: Position) -> dict[str, set[Position]]:
    bridge_tiles = {pos for pos, kind in room.dynamic_tiles.items() if kind == "bridge"}
    dynamic_gaps = {pos for pos, kind in room.dynamic_tiles.items() if kind == "gap"}
    visible_traps = {
        trap.pos
        for trap in room.traps.values()
        if trap.is_active and trap.pos not in bridge_tiles
    }
    abyss_tiles = {
        trap.pos
        for trap in room.traps.values()
        if trap.is_active and trap.trap_type == "abyss" and trap.pos not in bridge_tiles
    }
    return {
        "walls": set(room.walls),
        "chests": {
            chest.pos
            for chest in room.chests.values()
            if chest.is_visible and not chest.is_open
        },
        "opened_chests": {
            chest.pos
            for chest in room.chests.values()
            if chest.is_visible and chest.is_open
        },
        "exits": visible_exit_tiles(room, player_tile),
        "buttons": {button.pos for button in room.buttons.values()},
        "switches": {switch.pos for switch in room.switches.values()},
        "bridges": bridge_tiles,
        "gaps": dynamic_gaps | abyss_tiles,
        "traps": visible_traps,
        "monsters": {monster.tile_pos for monster in room.monsters.values()},
    }


def score_frame(obs, room, player_tile: Position, scores: dict[str, SetScore]) -> tuple[bool, bool]:
    static = extract_static_tiles(obs)
    dynamic = extract_dynamic_objects(obs)
    interactive = extract_interactive_tiles(obs)
    truth = room_truth(room, player_tile)

    predictions = {
        "walls": static.walls,
        "chests": static.chests,
        "opened_chests": static.opened_chests,
        "exits": static.exits,
        "buttons": interactive.buttons,
        "switches": interactive.switches,
        "bridges": interactive.bridges,
        "gaps": interactive.gaps,
        "traps": interactive.traps,
        "monsters": dynamic.monsters,
    }
    for name, predicted in predictions.items():
        scores[name].update(predicted, truth[name])
    return dynamic.player == player_tile, dynamic.monsters == truth["monsters"]


def evaluate_rooms(task_ids: Iterable[str], scores: dict[str, SetScore]) -> tuple[int, int, int]:
    frames = 0
    player_correct = 0
    monster_exact = 0
    for task_id in task_ids:
        env = make_env(task_id=task_id, observation_mode="pixels", control_mode="pixel")
        env.reset(seed=0)
        base = env.unwrapped
        runtime = base.engine.runtime
        manager = base.engine.room_manager

        for coord in manager.room_templates:
            room = manager.get_room(coord)
            runtime.room = room
            runtime.room_coord = coord
            player_tile = room.spawns[room.default_spawn_name]
            runtime.player.position_px = tile_to_top_left_px(player_tile)

            def record_frame() -> None:
                nonlocal frames, player_correct, monster_exact
                obs = base.render()[:MAP_PIXEL_HEIGHT, :MAP_PIXEL_WIDTH]
                player_ok, monsters_ok = score_frame(obs, room, player_tile, scores)
                frames += 1
                player_correct += int(player_ok)
                monster_exact += int(monsters_ok)

            record_frame()

            visible_chests = [chest for chest in room.chests.values() if chest.is_visible]
            interactive_objects = list(room.buttons.values()) + list(room.switches.values())
            if visible_chests or interactive_objects:
                for chest in visible_chests:
                    chest.is_open = True
                for interactive in interactive_objects:
                    interactive.is_pressed = True
                record_frame()
                for chest in visible_chests:
                    chest.is_open = False
                for interactive in interactive_objects:
                    interactive.is_pressed = False
        env.close()
    return frames, player_correct, monster_exact


def evaluate_random_frames(
    task_ids: Iterable[str],
    scores: dict[str, SetScore],
    *,
    steps: int,
    seed: int,
) -> tuple[int, int, int]:
    frames = 0
    player_correct = 0
    monster_exact = 0
    rng = random.Random(seed)
    for task_id in task_ids:
        env = make_env(
            task_id=task_id,
            observation_mode="pixels",
            control_mode="pixel",
            max_steps=max(steps + 1, 100),
        )
        obs, info = env.reset(seed=seed)
        for _ in range(steps):
            room = env.unwrapped.engine.runtime.room
            player_tile = tuple(info["agent"]["tile"])
            player_ok, monsters_ok = score_frame(obs, room, player_tile, scores)
            frames += 1
            player_correct += int(player_ok)
            monster_exact += int(monsters_ok)
            obs, _, terminated, truncated, info = env.step(rng.randrange(7))
            if terminated or truncated:
                break
        env.close()
    return frames, player_correct, monster_exact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="+", default=list(DEFAULT_TASKS))
    parser.add_argument("--random-steps", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    names = (
        "walls",
        "chests",
        "opened_chests",
        "exits",
        "buttons",
        "switches",
        "bridges",
        "gaps",
        "traps",
        "monsters",
    )
    scores = {name: SetScore() for name in names}
    room_stats = evaluate_rooms(args.tasks, scores)
    random_stats = evaluate_random_frames(
        args.tasks,
        scores,
        steps=max(0, args.random_steps),
        seed=args.seed,
    )
    frames = room_stats[0] + random_stats[0]
    player_correct = room_stats[1] + random_stats[1]
    monster_exact = room_stats[2] + random_stats[2]

    print(f"frames={frames}")
    print(f"player_tile_accuracy={player_correct / frames:.4f}")
    print(f"monster_set_exact_accuracy={monster_exact / frames:.4f}")
    for name in names:
        score = scores[name]
        print(
            f"{name:9s} precision={score.precision:.4f} recall={score.recall:.4f} "
            f"tp={score.true_positive} fp={score.false_positive} fn={score.false_negative}"
        )


if __name__ == "__main__":
    main()
