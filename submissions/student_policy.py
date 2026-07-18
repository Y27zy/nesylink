from __future__ import annotations

from typing import Any

from submissions.controllers import make_controller
from nesylink.core.constants import (
    ACTION_DOWN,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
)
from submissions.state import AgentMemory, SymbolicState
from submissions.vision import extract_symbolic_state


class Policy:
    """Unified policy entrypoint loaded by utils/evaluate_policy.py."""

    def __init__(self) -> None:
        self.task_id: str | None = None
        self.memory = AgentMemory()
        self.controller = make_controller(None)

    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        self.task_id = task_id
        self.memory = AgentMemory(seed=seed, task_id=task_id)
        self.controller = make_controller(task_id)
        self.memory.notes["controller"] = type(self.controller).__name__
        self.controller.reset(seed=seed, task_id=task_id)

    def act(self, obs: Any, info: dict[str, Any] | None = None) -> int:
        policy_info = info or {}
        received_task_id = policy_info.get("task_id")
        if isinstance(received_task_id, str) and received_task_id != self.task_id:
            self.task_id = received_task_id
            self.memory.task_id = received_task_id
            self.controller = make_controller(received_task_id)
            self.memory.notes["controller"] = type(self.controller).__name__
            self.controller.reset(task_id=received_task_id)

        # During final inference, do not use hidden info fields such as agent
        # coordinates, room id, entity counts, or dynamic-object truth.
        inventory = policy_info.get("inventory", {})
        self.memory.last_reward = float(policy_info.get("last_reward", 0.0) or 0.0)
        state = extract_symbolic_state(obs, self.memory, inventory=inventory)
        if self.task_id is None:
            inferred_task_id = _infer_task_id(state)
            if inferred_task_id is not None:
                self.task_id = inferred_task_id
                self.memory.task_id = inferred_task_id
                self.controller = make_controller(inferred_task_id)
                self.memory.notes["controller"] = type(self.controller).__name__
                self.memory.notes["inferred_task_id"] = inferred_task_id
                self.controller.reset(task_id=inferred_task_id)
        try:
            action = int(self.controller.act(state, self.memory))
        except (TypeError, ValueError):
            action = ACTION_NOOP
        self.memory.last_action = action
        if action in {ACTION_UP, ACTION_DOWN, ACTION_LEFT, ACTION_RIGHT}:
            self.memory.last_move_action = action
        return action


def make_policy() -> Policy:
    return Policy()


def _infer_task_id(state: SymbolicState) -> str | None:
    """Identify the task from permitted inventory and first-room symbols."""

    equipment = set(state.items) | set(state.tools)
    if "shield" in equipment and "sword" not in equipment:
        return "mathematical_logic/task_4"

    exit_labels = set(state.exit_types.values())
    exit_directions = {
        "west" if x == 0 else "east" if x == 9 else "north" if y == 0 else "south"
        for x, y in state.exits
    }
    if (
        state.buttons
        or len(exit_directions) >= 3
        or any(label in {"chest_gold", "chest_heal"} for label in state.chest_types.values())
    ):
        return "mathematical_logic/task_5"
    if "exit_conditional" in exit_labels:
        return "mathematical_logic/task_2"
    if "exit_normal" in exit_labels and "exit_locked_key" in exit_labels:
        return "mathematical_logic/task_3"
    if "exit_locked_key" in exit_labels and "chest_key" in state.chest_types.values():
        return "mathematical_logic/task_1"
    return None
