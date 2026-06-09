"""
算法抽象基类 — 定义所有求解器的统一接口。
"""

from abc import ABC, abstractmethod

from .models import ExamSession, Classroom, Student, ExamResult
from .constraint_engine import ConstraintConfig


class BaseSolver(ABC):
    """所有排座算法的抽象基类"""

    def __init__(self, config: ConstraintConfig):
        self.config = config

    @abstractmethod
    def solve(
        self,
        session: ExamSession,
        classrooms: list[Classroom],
        students: dict[str, Student],
    ) -> ExamResult:
        """返回符合约束的排座方案"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """算法名称"""
        ...

    @property
    @abstractmethod
    def energy_history(self) -> list[float]:
        """迭代过程中的 energy 值历史"""
        ...
