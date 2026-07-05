from __future__ import annotations

from nesylink.core.constants import ACTION_NOOP

from state import AgentMemory, SymbolicState


class Task3Controller:
    def reset(self, seed: int | None = None, task_id: str | None = None) -> None:
        del seed, task_id

    def act(self, state: SymbolicState, memory: AgentMemory) -> int:
        # TODO: cross monster hall -> open key chest -> return -> east locked exit.
        del state, memory
        return ACTION_NOOP

