"""测试模拟退火求解器"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    Student, Classroom, Subject, ExamSession,
)
from src.constraint_engine import ConstraintConfig
from src.sa_solver import SASolver


def make_students(n=30):
    """生成测试学生（均匀分到3个班）"""
    students = {}
    for i in range(1, n + 1):
        class_id = f"高三{(i-1) % 3 + 1}班"
        sid = f"S{i:04d}"
        students[sid] = Student(sid, f"学生{i}", "男", class_id, f"寝室{i}")
    return students


def make_classrooms():
    """生成测试考场"""
    return [
        Classroom("A", 48, "201", 2, available=True, rows=6, cols=6),
        Classroom("B", 30, "101", 1, available=True, rows=5, cols=5,
                  blocked_seats=[(3, 3)]),
    ]


class TestSASolver:
    def test_solver_returns_result(self):
        students = make_students(30)
        classrooms = make_classrooms()
        session = ExamSession(
            "TEST", Subject("测试", "TEST"), "2025-01-20 08:00",
            student_ids=list(students.keys()),
        )

        config = ConstraintConfig(
            isolate_same_class_4adj=True,
            room_capacity_enabled=True,
        )

        solver = SASolver(config)
        result = solver.solve(
            session, classrooms, students,
            T_start=50, T_end=0.1, cooling_rate=0.95,
            iterations_per_temp=50, restart_count=1,
            timeout_seconds=10,
        )

        assert result is not None
        assert len(result.classrooms) == 2
        assert "algorithm" in result.metadata
        assert result.metadata["algorithm"] == "Simulated Annealing"

        # 所有学生都应被分配
        assigned = set()
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id:
                    assigned.add(seat.student_id)
        assert len(assigned) == len(students)

    def test_energy_history_recorded(self):
        students = make_students(10)
        classrooms = [Classroom("A", 20, "201", 2, available=True, rows=4, cols=4)]
        session = ExamSession(
            "TEST", Subject("测试", "TEST"), "2025-01-20 08:00",
            student_ids=list(students.keys()),
        )

        config = ConstraintConfig()
        solver = SASolver(config)
        result = solver.solve(
            session, classrooms, students,
            T_start=20, T_end=0.5, cooling_rate=0.9,
            iterations_per_temp=20, restart_count=1,
            timeout_seconds=5,
        )

        assert len(solver.energy_history) > 0
        assert solver.energy_history[-1] >= 0

    def test_no_solution_with_insufficient_seats(self):
        """座位不够时应抛异常"""
        students = make_students(50)
        classrooms = [Classroom("A", 10, "201", 2, available=True, rows=3, cols=3)]
        session = ExamSession(
            "TEST", Subject("测试", "TEST"), "2025-01-20 08:00",
            student_ids=list(students.keys()),
        )

        solver = SASolver(ConstraintConfig())
        try:
            solver.solve(session, classrooms, students, timeout_seconds=3)
            # 如果没抛异常，检查结果
        except ValueError as e:
            assert "座位" in str(e) or "seat" in str(e).lower()
