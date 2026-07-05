from __future__ import annotations

from nesylink.core.constants import (
    ACTION_A,
    ACTION_LEFT,
    ACTION_NOOP,
    ACTION_RIGHT,
    ACTION_UP,
)

from state import AgentMemory, SymbolicState


def repeat(action: int, count: int) -> list[int]:
    return [action] * count


def build_reference_plan() -> list[int]:
    plan: list[int] = []
    plan += repeat(ACTION_RIGHT, 48)
    plan += repeat(ACTION_UP, 48)
    plan += repeat(ACTION_LEFT, 96)
    plan.append(ACTION_A)
    plan += repeat(ACTION_RIGHT, 32)
    plan += repeat(ACTION_UP, 48)
    plan += repeat(ACTION_RIGHT, 16)
    plan += repeat(ACTION_UP, 20)
    return plan


class Task1Controller:
    def __init__(self) -> None:
        self.plan = build_reference_plan()
        self.index = 0

    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id
        self.index = 0

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        del state, memory
        if self.index >= len(self.plan):
            return ACTION_NOOP
        action = self.plan[self.index]
        self.index += 1
        return action

