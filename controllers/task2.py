from __future__ import annotations

from nesylink.core.constants import ACTION_NOOP

from state import AgentMemory, SymbolicState


class Task2Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        # TODO: kill monster -> open key chest -> use west conditional exit.
        del state, memory
        return ACTION_NOOP

