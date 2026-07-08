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
    walls: set[Position] = field(default_factory=set)
    floors: set[Position] = field(default_factory=set)
    chests: set[Position] = field(default_factory=set)
    opened_chests: set[Position] = field(default_factory=set)
    exits: set[Position] = field(default_factory=set)
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
    notes: dict[str, Any] = field(default_factory=dict)
