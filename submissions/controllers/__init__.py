from __future__ import annotations

from .base import BaseController
from .task1 import Task1Controller
from .task2 import Task2Controller
from .task3 import Task3Controller
from .task4 import Task4Controller
from .task5 import Task5Controller


_CONTROLLER_BY_TASK = {
    "mathematical_logic/task_1": Task1Controller,
    "mathematical_logic/task_2": Task2Controller,
    "mathematical_logic/task_3": Task3Controller,
    "mathematical_logic/task_4": Task4Controller,
    "mathematical_logic/task_5": Task5Controller,
}


def make_controller(task_id: str | None) -> BaseController:
    controller_cls = _CONTROLLER_BY_TASK.get(task_id, BaseController)
    return controller_cls()


__all__ = [
    "BaseController",
    "Task1Controller",
    "Task2Controller",
    "Task3Controller",
    "Task4Controller",
    "Task5Controller",
    "make_controller",
]

