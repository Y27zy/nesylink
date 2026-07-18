from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Position = tuple[int, int]


@dataclass
class SymbolicState:
    """Tile-level state extracted from pixels.

    Coordinates are tile coordinates: x in 0..9, y in 0..7.
    """

    player: Position | None = None
    player_center_px: Position | None = None
    player_facing: str | None = None
    walls: set[Position] = field(default_factory=set)
    floors: set[Position] = field(default_factory=set)
    chests: set[Position] = field(default_factory=set)
    opened_chests: set[Position] = field(default_factory=set)
    exits: set[Position] = field(default_factory=set)
    chest_types: dict[Position, str] = field(default_factory=dict)
    exit_types: dict[Position, str] = field(default_factory=dict)
    monsters: set[Position] = field(default_factory=set)
    traps: set[Position] = field(default_factory=set)
    buttons: set[Position] = field(default_factory=set)
    switches: set[Position] = field(default_factory=set)
    bridges: set[Position] = field(default_factory=set)
    gaps: set[Position] = field(default_factory=set)
    keys: int = 0
    gold: int = 0
    items: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    equipped: dict[str, str] = field(default_factory=dict)
    raw_features: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoomBelief:
    """Persistent static knowledge for one visually identified room."""

    signature: tuple[Any, ...] = ()
    walls: set[Position] = field(default_factory=set)
    floors: set[Position] = field(default_factory=set)
    chests: set[Position] = field(default_factory=set)
    opened_chests: set[Position] = field(default_factory=set)
    exits: set[Position] = field(default_factory=set)
    chest_types: dict[Position, str] = field(default_factory=dict)
    exit_types: dict[Position, str] = field(default_factory=dict)
    traps: set[Position] = field(default_factory=set)
    buttons: set[Position] = field(default_factory=set)
    switches: set[Position] = field(default_factory=set)
    bridges: set[Position] = field(default_factory=set)
    gaps: set[Position] = field(default_factory=set)
    labels: dict[Position, str] = field(default_factory=dict)
    confidences: dict[Position, float] = field(default_factory=dict)
    pending_static: dict[tuple[str, Position], int] = field(default_factory=dict)
    first_seen_step: int = 0
    last_seen_step: int = 0


@dataclass
class AgentMemory:
    """Cross-step memory shared by vision, planner, and task controllers."""

    seed: int | None = None
    task_id: str | None = None
    step_count: int = 0
    current_room_key: str | None = None
    visited_rooms: set[str] = field(default_factory=set)
    opened_chests: set[Position] = field(default_factory=set)
    killed_monsters: set[Position] = field(default_factory=set)
    button_history: set[Position] = field(default_factory=set)
    bridge_state_hint: str | None = None
    planned_actions: list[int] = field(default_factory=list)
    room_beliefs: dict[str, RoomBelief] = field(default_factory=dict)
    active_vision_room_key: str | None = None
    last_player: Position | None = None
    last_player_center_px: Position | None = None
    last_player_bbox: tuple[int, int, int, int] | None = None
    last_player_facing: str | None = None
    player_miss_count: int = 0
    monster_tracks: dict[str, dict[Position, int]] = field(default_factory=dict)
    last_action: int | None = None
    last_move_action: int | None = None
    last_reward: float = 0.0
    notes: dict[str, Any] = field(default_factory=dict)
