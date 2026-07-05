from __future__ import annotations

from typing import Any

from controllers import make_controller
from state import AgentMemory
from vision import extract_symbolic_state


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
        self.controller.reset(seed=seed, task_id=task_id)

    def act(self, obs: Any, info: dict[str, Any] | None = None) -> int:
        # During final inference, do not use hidden info fields such as agent
        # coordinates, room id, entity counts, or dynamic-object truth.
        inventory = (info or {}).get("inventory", {})
        state = extract_symbolic_state(obs, self.memory, inventory=inventory)
        return self.controller.act(state, self.memory)


def make_policy() -> Policy:
    return Policy()

