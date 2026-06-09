"""测试蚁群算法求解器"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Student, Classroom, Subject, ExamSession
from src.constraint_engine import ConstraintConfig
from src.aco_solver import ACOSolver


def test_aco_basic():
    """ACO 基本求解"""
    students = {}
    for i in range(1, 16):
        class_id = f"高三{(i-1) % 3 + 1}班"
        sid = f"S{i:04d}"
        students[sid] = Student(sid, f"学生{i}", "男", class_id, f"寝室{i}")

    classrooms = [
        Classroom("A", 25, "201", 2, available=True, rows=5, cols=5),
    ]
    session = ExamSession(
        "TEST", Subject("测试", "TEST"), "2025-01-20 08:00",
        student_ids=list(students.keys()),
    )

    config = ConstraintConfig(isolate_same_class_4adj=True)
    solver = ACOSolver(config)
    result = solver.solve(
        session, classrooms, students,
        n_ants=5, n_iterations=30, evaporation_rate=0.1,
        timeout_seconds=10,
    )

    assert result is not None
    assert len(result.classrooms) == 1
    assert result.metadata["algorithm"] == "Ant Colony Optimization"

    # 检查分配
    assigned = set()
    for cr in result.classrooms:
        for seat in cr.seats:
            if seat.student_id:
                assigned.add(seat.student_id)
    assert len(assigned) == len(students)


def test_aco_energy_history():
    """ACO 记录 energy 历史"""
    students = {}
    for i in range(1, 6):
        sid = f"S{i:04d}"
        students[sid] = Student(sid, f"学生{i}", "男", "高三1班", f"寝室{i}")

    classrooms = [Classroom("A", 10, "201", 2, available=True, rows=3, cols=3)]
    session = ExamSession(
        "TEST", Subject("测试", "TEST"), "2025-01-20 08:00",
        student_ids=list(students.keys()),
    )

    solver = ACOSolver(ConstraintConfig())
    solver.solve(session, classrooms, students, n_ants=3, n_iterations=10, timeout_seconds=5)

    assert len(solver.energy_history) > 0
