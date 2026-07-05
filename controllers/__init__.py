from __future__ import annotations

from .base import BaseController
from .task1 import Task1Controller
from .task2 import Task2Controller
from .task3 import Task3Controller
from .task4 import Task4Controller
from .task5 import Task5Controller


def make_controller(task_id: str | None) -> BaseController:
    if task_id == "mathematical_logic/task_1":
        return Task1Controller()
    if task_id == "mathematical_logic/task_2":
        return Task2Controller()
    if task_id == "mathematical_logic/task_3":
        return Task3Controller()
    if task_id == "mathematical_logic/task_4":
        return Task4Controller()
    if task_id == "mathematical_logic/task_5":
        return Task5Controller()
    return BaseController()


__all__ = [
    "BaseController",
    "Task1Controller",
    "Task2Controller",
    "Task3Controller",
    "Task4Controller",
    "Task5Controller",
    "make_controller",
]

