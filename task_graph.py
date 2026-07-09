
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator


@dataclass
class TaskNode:
    name: str
    prereqs: set[str] = field(default_factory=set)
    action_gen: Callable[..., Iterator[int | None]] = lambda _state, _mem: iter([])
    room:str = ""


class TaskGraph:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskNode] = {}

    def add_task(
        self,
        name: str,
        *,
        prereqs: set[str] | None = None,
        action_gen: Callable[..., Iterator[int | None]] | None = None,
        room:str = "",
    ) -> TaskNode:

        node = self._tasks.get(name)
        if node is None:
            node = TaskNode(name=name)
            self._tasks[name] = node

        if prereqs is not None:
            node.prereqs = prereqs

        if action_gen is not None:
            node.action_gen = action_gen

        if room is not None:
            node.room = room

        return node

    def remove_task(self, name: str) -> None:
        self._tasks.pop(name, None)

    def get(self, name: str) -> TaskNode | None:
        return self._tasks.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tasks
