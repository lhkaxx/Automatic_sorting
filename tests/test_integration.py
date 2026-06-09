"""集成测试 — 端到端排座流程"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Student, Classroom, Subject, ExamSession, ExamResult
from src.constraint_engine import ConstraintConfig, validate
from src.sa_solver import SASolver
from src.evaluator import Evaluator


def test_full_pipeline_small():
    """小规模端到端测试：10学生 + 2考场 + SA + 评估"""
    # 生成数据
    students = {}
    for i in range(1, 11):
        class_id = f"高三{(i-1) % 3 + 1}班"
        sid = f"S{i:04d}"
        students[sid] = Student(sid, f"学生{i}", "男", class_id, f"寝室{i}")

    classrooms = [
        Classroom("A", 10, "201", 2, available=True, rows=3, cols=3),
        Classroom("B", 6, "101", 1, available=True, rows=2, cols=2),
    ]

    session = ExamSession(
        "TEST_INT", Subject("数学", "MATH"), "2025-01-20 08:00",
        student_ids=list(students.keys()),
    )

    # 配置
    config = ConstraintConfig(
        isolate_same_class_4adj=True,
        room_capacity_enabled=True,
    )

    # 求解
    solver = SASolver(config)
    result = solver.solve(
        session, classrooms, students,
        T_start=50, T_end=0.1, cooling_rate=0.95,
        iterations_per_temp=50, restart_count=2,
        timeout_seconds=10,
    )

    # 验证结果
    assert isinstance(result, ExamResult)
    assert result.metadata["algorithm"] == "Simulated Annealing"

    # 所有学生都被分配
    assigned = set()
    for cr in result.classrooms:
        for seat in cr.seats:
            if seat.student_id:
                assigned.add(seat.student_id)
    assert len(assigned) == len(students), f"Missing: {set(students) - assigned}"

    # 验证无重复分配
    assert len(assigned) == 10

    # 验证约束
    passed, violations = validate(result, students, {}, config)
    assert passed, f"Violations: {violations[:5]}"

    # 评估
    evaluator = Evaluator()
    report = evaluator.evaluate(result, students, config, solver.energy_history)

    assert report.constraint_pass_rate > 0.5
    assert report.class_isolation_score >= 0.0
    assert len(report.room_utilization) == 2
    assert len(report.energy_curve) > 0
