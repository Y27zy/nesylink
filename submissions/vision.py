from __future__ import annotations

from dataclasses import replace
from hashlib import sha1
from typing import Any

import numpy as np

from nesylink.core.constants import (
    ACTION_A,
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
)

from .state import AgentMemory, RoomBelief, SymbolicState
from .vision_dynamic_resnet import (
    DynamicObject,
    DynamicVisionResult,
    detect_dynamic_components,
    extract_dynamic_objects,
    replace_dynamic_player,
)
from .vision_static_resnet import (
    LABEL_TO_INDEX,
    StaticVisionResult,
    extract_static_tiles,
    is_chest_label,
)


_COMPONENT_PLAYER_FALLBACK_TASKS = {"mathematical_logic/task_4"}


TILE_SIZE = 16
ROOM_WIDTH_TILES = 10
ROOM_HEIGHT_TILES = 8


def extract_symbolic_state(
    obs: Any,
    memory: AgentMemory,
    *,
    inventory: dict[str, Any] | None = None,
) -> SymbolicState:
    """Fuse current pixel detections with persistent room-level beliefs."""

    memory.step_count += 1
    inv = inventory or {}
    state = SymbolicState(
        keys=int(inv.get("keys", 0) or 0),
        gold=int(inv.get("gold", 0) or 0),
        items=tuple(str(item) for item in inv.get("items", ()) or ()),
        tools=tuple(str(item) for item in inv.get("tools", ()) or ()),
        equipped=dict(inv.get("equipped", {}) or {}),
    )
    if not isinstance(obs, np.ndarray):
        return state

    state.raw_features["obs_shape"] = tuple(obs.shape)
    state.raw_features["obs_dtype"] = str(obs.dtype)

    raw_dynamic = extract_dynamic_objects(obs)
    observed_static = extract_static_tiles(obs)
    selected_dynamic = _select_dynamic_candidates(raw_dynamic, observed_static, memory)
    if (
        selected_dynamic.player is None
        and memory.task_id in _COMPONENT_PLAYER_FALLBACK_TASKS
    ):
        component_dynamic = detect_dynamic_components(obs)
        if component_dynamic.player is not None:
            selected_dynamic = replace_dynamic_player(
                selected_dynamic,
                component_dynamic,
            )
    dynamic = _stabilize_dynamic(selected_dynamic, memory)
    current_static = _remove_dynamic_overlays(observed_static, dynamic)
    static, vision_room_key = _fuse_room_belief(
        current_static,
        memory,
        monsters_visible=bool(dynamic.monsters),
    )
    dynamic = _remove_fused_static_artifacts(dynamic, static)
    dynamic = _stabilize_monsters(dynamic, memory, vision_room_key)

    state.player = dynamic.player
    state.player_facing = dynamic.player_facing
    player_objects = [
        obj
        for obj in dynamic.objects
        if obj.kind == "player" and obj.tile == dynamic.player
    ]
    if player_objects:
        state.player_center_px = max(player_objects, key=lambda obj: obj.confidence).center_px
    elif memory.last_player_center_px is not None:
        state.player_center_px = memory.last_player_center_px
    state.monsters = dynamic.monsters

    state.walls = static.walls
    state.floors = static.floors
    state.chests = static.chests
    state.opened_chests = static.opened_chests
    state.exits = static.exits
    state.chest_types = static.chest_types
    state.exit_types = static.exit_types
    state.traps = static.traps
    state.buttons = static.buttons
    state.switches = static.switches
    state.bridges = static.bridges
    state.gaps = static.gaps

    state.raw_features.update(
        {
            "static_vision_backend": static.backend,
            "static_labels": static.labels,
            "static_label_ids": static.label_ids,
            "static_confidences": static.confidences,
            "static_uncertain": static.uncertain,
            "pressed_buttons": static.pressed_buttons,
            "activated_switches": static.activated_switches,
            "dynamic_vision_backend": dynamic.backend,
            "dynamic_objects": dynamic.objects,
            "player_bbox": dynamic.player_bbox,
            "player_facing": dynamic.player_facing,
            "vision_room_key": vision_room_key,
            "vision_room_count": len(memory.room_beliefs),
        }
    )
    return state


def _remove_fused_static_artifacts(
    dynamic: DynamicVisionResult,
    static: StaticVisionResult,
) -> DynamicVisionResult:
    """Apply room-memory structure constraints before creating monster tracks."""

    artifacts = static.exits | static.bridges
    objects = [
        obj
        for obj in dynamic.objects
        if obj.kind == "player" or obj.tile not in artifacts
    ]
    monsters = {obj.tile for obj in objects if obj.kind != "player"}
    if monsters == dynamic.monsters and len(objects) == len(dynamic.objects):
        return dynamic
    return replace(
        dynamic,
        monsters=monsters,
        objects=objects,
        backend=f"{dynamic.backend}+room_structure",
    )


def _stabilize_dynamic(
    current: DynamicVisionResult,
    memory: AgentMemory,
) -> DynamicVisionResult:
    if current.player is not None:
        memory.last_player = current.player
        memory.last_player_bbox = current.player_bbox
        memory.last_player_facing = current.player_facing or memory.last_player_facing
        player = max(
            (
                obj
                for obj in current.objects
                if obj.kind == "player" and obj.tile == current.player
            ),
            key=lambda obj: obj.confidence,
            default=None,
        )
        if player is not None:
            memory.last_player_center_px = player.center_px
        memory.player_miss_count = 0
        return current

    memory.player_miss_count += 1
    if memory.last_player is None:
        return current
    if memory.player_miss_count > 96:
        if memory.last_action != ACTION_NOOP:
            return current
        memory.player_miss_count = 0

    wrapped = _wrapped_player_tile(
        memory.last_player,
        memory.last_action,
        room_changed=memory.last_reward > 5.0,
    )
    center = (
        tile_center_px(wrapped)
        if wrapped is not None
        else memory.last_player_center_px or tile_center_px(memory.last_player)
    )
    dx, dy = {
        ACTION_UP: (0, -1),
        ACTION_DOWN: (0, 1),
        ACTION_LEFT: (-1, 0),
        ACTION_RIGHT: (1, 0),
    }.get(memory.last_action, (0, 0))
    if wrapped is None:
        center = (
            min(max(center[0] + dx, 0), ROOM_WIDTH_TILES * TILE_SIZE - 1),
            min(max(center[1] + dy, 0), ROOM_HEIGHT_TILES * TILE_SIZE - 1),
        )
    tile = pixel_to_tile(*center)
    bbox = (center[0] - 8, center[1] - 8, center[0] + 8, center[1] + 8)
    predicted = DynamicObject(
        kind="player",
        tile=tile,
        center_px=center,
        bbox=bbox,
        confidence=max(0.2, 0.65 - memory.player_miss_count * 0.15),
    )
    memory.last_player = tile
    memory.last_player_center_px = center
    memory.last_player_bbox = bbox
    return replace(
        current,
        player=tile,
        player_bbox=bbox,
        player_facing=memory.last_player_facing,
        objects=current.objects + [predicted],
        backend=f"{current.backend}+temporal",
    )


def _select_dynamic_candidates(
    dynamic: DynamicVisionResult,
    static: StaticVisionResult,
    memory: AgentMemory,
) -> DynamicVisionResult:
    """Reject exit-shaped player peaks unless motion history supports them."""

    static_objects = set(static.chests) | set(static.buttons) | set(static.switches)
    static_objects.update(
        pos for pos, label in static.labels.items() if label == "npc"
    )
    combat_context = (
        memory.notes.get("search_plan_kind") in {"attack", "monster"}
        or memory.notes.get("task2_phase") == "kill_monster"
        or memory.notes.get("task3_phase") == "handle_monster"
    )
    if memory.last_action == ACTION_A and memory.last_reward > 5.0 and combat_context:
        memory.notes["vision_recent_kill"] = (
            memory.last_player,
            memory.step_count + 48,
        )
    recent_kill = memory.notes.get("vision_recent_kill")
    recent_kill_center = None
    if (
        isinstance(recent_kill, tuple)
        and len(recent_kill) == 2
        and recent_kill[0] is not None
        and memory.step_count <= int(recent_kill[1])
    ):
        recent_kill_center = recent_kill[0]
    filtered_objects = [
        obj
        for obj in dynamic.objects
        if not (
            obj.kind != "player"
            and (
                (
                    recent_kill_center is not None
                    and abs(obj.tile[0] - recent_kill_center[0])
                    + abs(obj.tile[1] - recent_kill_center[1])
                    <= 1
                )
                or (
                    obj.tile in (static.exits | static.bridges)
                )
                or (
                    obj.confidence < 0.55
                    and obj.tile in (static.exits | static.bridges)
                )
                or (
                    obj.confidence < 0.5
                    and any(
                        abs(obj.tile[0] - pos[0]) + abs(obj.tile[1] - pos[1]) <= 1
                        for pos in static_objects
                    )
                )
            )
        )
    ]
    players = [obj for obj in filtered_objects if obj.kind == "player"]
    if not players:
        movement_action = (
            memory.last_action
            if memory.last_action in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}
            else memory.last_move_action
        )
        if memory.last_player is not None:
            predicted_centers = _predicted_player_centers(
                memory,
                movement_action,
                None,
            )
            filtered_objects = [
                obj
                for obj in filtered_objects
                if obj.kind == "player"
                or not any(
                    max(
                        abs(obj.center_px[0] - point[0]),
                        abs(obj.center_px[1] - point[1]),
                    )
                    <= 10
                    for point in predicted_centers
                )
            ]
        monsters = {obj.tile for obj in filtered_objects if obj.kind != "player"}
        memory.notes["vision_previous_monsters"] = monsters
        return replace(
            dynamic,
            monsters=monsters,
            objects=filtered_objects,
        )
    best = max(players, key=lambda obj: obj.confidence)
    if memory.last_player is not None:
        previous = memory.last_player
        movement_action = (
            memory.last_action
            if memory.last_action in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}
            else memory.last_move_action
        )
        expected = [previous]
        wrapped = _wrapped_player_tile(
            previous,
            movement_action,
            room_changed=memory.last_reward > 5.0,
        )
        if wrapped is not None:
            expected.append(wrapped)
        compatible_players = [
            obj
            for obj in players
            if _motion_compatible(previous, obj.tile, movement_action)
            or (wrapped is not None and obj.tile == wrapped)
        ]
        temporal_pool = compatible_players or players
        predicted_centers = _predicted_player_centers(memory, movement_action, wrapped)
        temporal_best = min(
            temporal_pool,
            key=lambda obj: (
                min(
                    abs(obj.center_px[0] - point[0])
                    + abs(obj.center_px[1] - point[1])
                    for point in predicted_centers
                ),
                -obj.confidence,
            ),
        )
        temporal_pixel_distance = min(
            abs(temporal_best.center_px[0] - point[0])
            + abs(temporal_best.center_px[1] - point[1])
            for point in predicted_centers
        )
        best_distance = min(
            abs(best.tile[0] - point[0]) + abs(best.tile[1] - point[1])
            for point in expected
        )
        temporal_distance = min(
            abs(temporal_best.tile[0] - point[0]) + abs(temporal_best.tile[1] - point[1])
            for point in expected
        )
        transition_candidate = wrapped is not None and (
            abs(temporal_best.tile[0] - wrapped[0])
            + abs(temporal_best.tile[1] - wrapped[1])
            <= 2
        )
        if compatible_players and (
            temporal_pixel_distance <= 12 or best_distance > 1
        ):
            best = temporal_best
        elif temporal_distance + 1 < best_distance and transition_candidate:
            best = temporal_best
        selected_distance = min(
            abs(best.tile[0] - point[0]) + abs(best.tile[1] - point[1])
            for point in expected
        )
        implausible_static_peak = best.tile in (static.exits | static.bridges)
        selected_pixel_distance = min(
            abs(best.center_px[0] - point[0]) + abs(best.center_px[1] - point[1])
            for point in predicted_centers
        )
        supported_transition = (
            wrapped is not None
            and abs(best.tile[0] - wrapped[0]) + abs(best.tile[1] - wrapped[1]) <= 1
            and best.confidence >= 0.8
            and not implausible_static_peak
        )
        impossible_motion = (
            selected_distance > (2 if wrapped is not None else 1)
            and not supported_transition
        )
        implausible_pixel_jump = (
            selected_pixel_distance > 12 and implausible_static_peak
        )
        implausible_short_motion = (
            selected_distance <= 2
            and not _motion_compatible(previous, best.tile, movement_action)
            and not supported_transition
            and memory.last_reward > -0.5
        )
        if (
            impossible_motion
            or (
                selected_distance > 3
                and (best.confidence < 0.2 or implausible_static_peak)
            )
            or implausible_pixel_jump
            or implausible_short_motion
        ):
            return replace(
                dynamic,
                player=None,
                player_bbox=None,
                player_facing=None,
                monsters={obj.tile for obj in filtered_objects if obj.kind != "player"},
                objects=filtered_objects,
                backend=f"{dynamic.backend}+symbolic_reject",
            )
    filtered_objects = _remove_new_player_overlaps(
        filtered_objects,
        best,
    )
    monsters = {obj.tile for obj in filtered_objects if obj.kind != "player"}
    memory.notes["vision_previous_monsters"] = monsters
    return replace(
        dynamic,
        player=best.tile,
        player_bbox=best.bbox,
        player_facing=dynamic.player_facing if best.tile == dynamic.player else None,
        monsters=monsters,
        objects=filtered_objects,
        backend=(
            dynamic.backend
            if best.tile == dynamic.player and len(filtered_objects) == len(dynamic.objects)
            else f"{dynamic.backend}+symbolic_filter"
        ),
    )


def _remove_new_player_overlaps(
    objects: list[DynamicObject],
    player: DynamicObject,
) -> list[DynamicObject]:
    """Drop a new monster peak produced by the moving player sprite itself."""

    result: list[DynamicObject] = []
    for obj in objects:
        if obj.kind == "player":
            result.append(obj)
            continue
        overlaps_player = max(
            abs(obj.center_px[0] - player.center_px[0]),
            abs(obj.center_px[1] - player.center_px[1]),
        ) <= 10
        if not overlaps_player:
            result.append(obj)
    return result


def _wrapped_player_tile(
    previous: Position,
    action: int | None,
    *,
    room_changed: bool,
) -> Position | None:
    if not room_changed:
        return None
    if action == ACTION_UP and previous[1] <= 1:
        return (previous[0], ROOM_HEIGHT_TILES - 2)
    if action == ACTION_DOWN and previous[1] >= ROOM_HEIGHT_TILES - 2:
        return (previous[0], 1)
    if action == ACTION_LEFT and previous[0] <= 1:
        return (ROOM_WIDTH_TILES - 2, previous[1])
    if action == ACTION_RIGHT and previous[0] >= ROOM_WIDTH_TILES - 2:
        return (1, previous[1])
    return None


def _predicted_player_centers(
    memory: AgentMemory,
    movement_action: int | None,
    wrapped: Position | None,
) -> list[Position]:
    center = memory.last_player_center_px or tile_center_px(memory.last_player or (0, 0))
    dx, dy = {
        ACTION_UP: (0, -1),
        ACTION_DOWN: (0, 1),
        ACTION_LEFT: (-1, 0),
        ACTION_RIGHT: (1, 0),
    }.get(movement_action, (0, 0))
    predicted = [(center[0] + dx, center[1] + dy)]
    if wrapped is not None:
        predicted.append(tile_center_px(wrapped))
    return predicted


def _motion_compatible(
    previous: Position,
    candidate: Position,
    action: int | None,
) -> bool:
    if candidate == previous:
        return True
    allowed = {
        ACTION_UP: (previous[0], previous[1] - 1),
        ACTION_DOWN: (previous[0], previous[1] + 1),
        ACTION_LEFT: (previous[0] - 1, previous[1]),
        ACTION_RIGHT: (previous[0] + 1, previous[1]),
    }.get(action)
    return allowed is None or candidate == allowed


def _stabilize_monsters(
    current: DynamicVisionResult,
    memory: AgentMemory,
    room_key: str,
) -> DynamicVisionResult:
    """Carry room-local monster detections through brief sprite occlusion."""

    previous = memory.monster_tracks.get(room_key, {})
    tracks: dict[Position, int] = {}
    for pos, remaining in previous.items():
        matched = any(
            abs(pos[0] - seen[0]) + abs(pos[1] - seen[1]) <= 2
            for seen in current.monsters
        )
        if not matched and remaining > 1:
            tracks[pos] = remaining - 1
    strong = {
        obj.tile
        for obj in current.objects
        if obj.kind != "player" and obj.confidence >= 0.65
    }
    for pos in current.monsters:
        inherited = max(
            (
                remaining - 1
                for old_pos, remaining in previous.items()
                if abs(old_pos[0] - pos[0]) + abs(old_pos[1] - pos[1]) <= 2
            ),
            default=3,
        )
        tracks[pos] = 24 if pos in strong else max(3, inherited)
    memory.monster_tracks[room_key] = tracks

    monsters = set(tracks)
    if monsters == current.monsters:
        return current
    objects = list(current.objects)
    represented = {obj.tile for obj in objects if obj.kind != "player"}
    for pos in monsters - represented:
        center = tile_center_px(pos)
        objects.append(
            DynamicObject(
                kind="monster_chaser",
                tile=pos,
                center_px=center,
                bbox=(center[0] - 8, center[1] - 8, center[0] + 8, center[1] + 8),
                confidence=0.25,
            )
        )
    return replace(
        current,
        monsters=monsters,
        objects=objects,
        backend=f"{current.backend}+temporal_monsters",
    )


def _remove_dynamic_overlays(
    static: StaticVisionResult,
    dynamic: DynamicVisionResult,
) -> StaticVisionResult:
    """Prevent a foreground sprite from becoming a remembered static object."""

    exact_occupied = set(dynamic.monsters)
    object_occupied = set(exact_occupied)
    occupied = set(exact_occupied)
    if dynamic.player is not None:
        px, py = dynamic.player
        exact_occupied.add(dynamic.player)
        object_occupied.add(dynamic.player)
        nearby_players = {
            obj.tile
            for obj in dynamic.objects
            if obj.kind == "player"
            and obj.confidence >= 0.8
            and abs(obj.tile[0] - px) + abs(obj.tile[1] - py) <= 1
        }
        object_occupied.update(nearby_players)
        for ox, oy in object_occupied:
            occupied.update(
                {
                    (ox, oy),
                    (ox - 1, oy),
                    (ox + 1, oy),
                    (ox, oy - 1),
                    (ox, oy + 1),
                }
            )
    labels = dict(static.labels)
    label_ids = dict(static.label_ids)
    confidences = dict(static.confidences)
    chests = set(static.chests)
    opened_chests = set(static.opened_chests)
    chest_types = dict(static.chest_types)
    exits = set(static.exits)
    exit_types = dict(static.exit_types)
    buttons = set(static.buttons)
    pressed_buttons = set(static.pressed_buttons)
    switches = set(static.switches)
    activated_switches = set(static.activated_switches)
    uncertain = set(static.uncertain)

    for pos in occupied:
        label = labels.get(pos, "floor")
        foreground_object = (
            (is_chest_label(label) and pos in object_occupied)
            or label.startswith("exit_")
        )
        if label in {"button", "switch", "npc"} or foreground_object:
            labels[pos] = "floor"
            label_ids[pos] = LABEL_TO_INDEX["floor"]
            confidences[pos] = 0.0
            uncertain.add(pos)
            chests.discard(pos)
            opened_chests.discard(pos)
            chest_types.pop(pos, None)
            exits.discard(pos)
            exit_types.pop(pos, None)
            buttons.discard(pos)
            pressed_buttons.discard(pos)
            switches.discard(pos)
            activated_switches.discard(pos)
    return replace(
        static,
        chests=chests,
        opened_chests=opened_chests,
        chest_types=chest_types,
        exits=exits,
        exit_types=exit_types,
        buttons=buttons,
        pressed_buttons=pressed_buttons,
        switches=switches,
        activated_switches=activated_switches,
        labels=labels,
        label_ids=label_ids,
        confidences=confidences,
        uncertain=uncertain,
    )


def _fuse_room_belief(
    current: StaticVisionResult,
    memory: AgentMemory,
    *,
    monsters_visible: bool,
) -> tuple[StaticVisionResult, str]:
    signature = _room_signature(current)
    key = "vision_" + sha1(repr(signature).encode("ascii")).hexdigest()[:12]
    belief = memory.room_beliefs.get(key)
    if belief is None:
        for known_key, candidate in memory.room_beliefs.items():
            if _same_room_signature(signature, candidate.signature):
                key = known_key
                belief = candidate
                break
    if belief is None:
        belief = RoomBelief(
            signature=signature,
            walls=set(current.walls),
            floors=set(current.floors),
            chests=set(current.chests),
            opened_chests=set(current.opened_chests),
            exits=set(current.exits),
            chest_types=dict(current.chest_types),
            exit_types=dict(current.exit_types),
            traps=set(current.traps),
            buttons=set(current.buttons),
            switches=set(current.switches),
            bridges=set(current.bridges),
            gaps=set(current.gaps),
            labels=dict(current.labels),
            confidences=dict(current.confidences),
            first_seen_step=memory.step_count,
            last_seen_step=memory.step_count,
        )
        memory.room_beliefs[key] = belief
    else:
        belief.last_seen_step = memory.step_count
        belief.floors.update(current.floors)
        _merge_confirmed_static(
            belief,
            "chest",
            belief.chests,
            current.chests,
            current,
            allow_new=(
                not monsters_visible
                and bool(memory.notes.get("expect_new_static_chest"))
            ),
            required_frames=8,
        )
        _merge_confirmed_static(belief, "exit", belief.exits, current.exits, current)
        _merge_confirmed_static(
            belief,
            "button",
            belief.buttons,
            current.buttons,
            current,
            required_frames=8,
        )
        _merge_confirmed_static(
            belief,
            "switch",
            belief.switches,
            current.switches,
            current,
            required_frames=8,
        )
        belief.opened_chests.update(current.opened_chests & belief.chests)
        belief.chest_types.update(
            {pos: label for pos, label in current.chest_types.items() if pos in belief.chests}
        )
        belief.exit_types.update(
            {pos: label for pos, label in current.exit_types.items() if pos in belief.exits}
        )
        # Hazards and bridges can change at runtime, so use the current state.
        belief.traps = set(current.traps)
        belief.bridges = set(current.bridges)
        belief.gaps = set(current.gaps)
        for pos, label in current.labels.items():
            old_label = belief.labels.get(pos)
            confidence = current.confidences.get(pos, 0.0)
            old_confidence = belief.confidences.get(pos, 0.0)
            if confidence >= 0.55 and (
                old_label in {None, "floor"} or label != "floor" or confidence >= old_confidence
            ):
                belief.labels[pos] = label
                belief.confidences[pos] = confidence

    memory.active_vision_room_key = key
    fused_labels = dict(current.labels)
    fused_labels.update(belief.labels)
    fused_confidences = dict(current.confidences)
    fused_confidences.update(belief.confidences)
    fused = replace(
        current,
        walls=set(belief.walls),
        floors=set(belief.floors),
        chests=set(belief.chests),
        opened_chests=set(belief.opened_chests),
        exits=set(belief.exits),
        chest_types=dict(belief.chest_types),
        exit_types=dict(belief.exit_types),
        traps=set(belief.traps),
        buttons=set(belief.buttons),
        switches=set(belief.switches),
        bridges=set(belief.bridges),
        gaps=set(belief.gaps),
        labels=fused_labels,
        label_ids={pos: LABEL_TO_INDEX.get(label, 0) for pos, label in fused_labels.items()},
        confidences=fused_confidences,
    )
    return fused, key


def _merge_confirmed_static(
    belief: RoomBelief,
    kind: str,
    known: set[Position],
    observed: set[Position],
    current: StaticVisionResult,
    *,
    allow_new: bool = True,
    required_frames: int = 3,
) -> None:
    """Require repeated evidence before adding a new persistent object."""

    for candidate in list(belief.pending_static):
        candidate_kind, pos = candidate
        if candidate_kind == kind and pos not in observed:
            belief.pending_static.pop(candidate, None)
    if not allow_new:
        for candidate in list(belief.pending_static):
            if candidate[0] == kind:
                belief.pending_static.pop(candidate, None)
        return
    for pos in observed - known:
        confidence = current.confidences.get(pos, 0.0)
        if confidence < 0.6:
            continue
        if kind == "exit":
            direction = _boundary_direction(pos)
            known_in_direction = sum(
                _boundary_direction(existing) == direction
                for existing in known
            )
            if direction is not None and known_in_direction >= 2:
                continue
        candidate = (kind, pos)
        count = belief.pending_static.get(candidate, 0) + 1
        if count >= required_frames:
            known.add(pos)
            belief.pending_static.pop(candidate, None)
        else:
            belief.pending_static[candidate] = count


def _boundary_direction(pos: Position) -> str | None:
    x, y = pos
    if y == 0:
        return "north"
    if x == ROOM_WIDTH_TILES - 1:
        return "east"
    if y == ROOM_HEIGHT_TILES - 1:
        return "south"
    if x == 0:
        return "west"
    return None


def _room_signature(static: StaticVisionResult) -> tuple[Any, ...]:
    exits_by_direction: dict[str, set[str]] = {}
    for x, y in static.exits:
        direction = _boundary_direction((x, y))
        if direction is not None:
            exits_by_direction.setdefault(direction, set()).add(
                static.exit_types.get((x, y), "exit_normal")
            )
    exit_signature = tuple(
        (direction, tuple(sorted(labels)))
        for direction, labels in sorted(exits_by_direction.items())
    )
    return tuple(sorted(static.walls)), exit_signature


def _same_room_signature(
    left: tuple[Any, ...],
    right: tuple[Any, ...],
) -> bool:
    left_walls, left_exits = left
    right_walls, right_exits = right
    if left_walls != right_walls:
        return False
    return left_exits == right_exits


def tile_center_px(pos: tuple[int, int]) -> tuple[int, int]:
    return (pos[0] * TILE_SIZE + TILE_SIZE // 2, pos[1] * TILE_SIZE + TILE_SIZE // 2)


def pixel_to_tile(x: int, y: int) -> tuple[int, int]:
    return (x // TILE_SIZE, y // TILE_SIZE)
