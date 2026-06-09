"""测试约束引擎"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    Student, Classroom, Subject, ExamSession, ExamResult,
    ClassroomResult, SeatAssignment,
)
from src.constraint_engine import ConstraintConfig, validate, count_violations
from src.seat_graph import SeatGraph


def make_result(room_id="A201", rows=3, cols=3, assignments=None):
    """构建简单的 ExamResult"""
    session = ExamSession("TEST", Subject("测试", "TEST"), "2025-01-20 08:00")
    seats = []
    if assignments:
        for r, c, sid in assignments:
            seats.append(SeatAssignment(room_id, r, c, sid))
    cr = ClassroomResult(room_id, rows, cols, seats=seats)
    return ExamResult(session, classrooms=[cr])


class TestClassIsolation:
    def test_four_adj_no_violation(self):
        """不同班级坐相邻 — 无违规"""
        s1 = Student("S1", "张三", "男", "高三1班", "")
        s2 = Student("S2", "李四", "女", "高三2班", "")
        students = {"S1": s1, "S2": s2}

        result = make_result("A201", 3, 3, [
            (1, 1, "S1"), (1, 2, "S2"),
        ])

        config = ConstraintConfig(isolate_same_class_4adj=True)
        passed, violations = validate(result, students, {}, config)
        assert passed

    def test_four_adj_violation(self):
        """同班坐相邻 — 违规"""
        s1 = Student("S1", "张三", "男", "高三1班", "")
        s2 = Student("S2", "李四", "女", "高三1班", "")
        students = {"S1": s1, "S2": s2}

        result = make_result("A201", 3, 3, [
            (1, 1, "S1"), (1, 2, "S2"),
        ])

        config = ConstraintConfig(isolate_same_class_4adj=True)
        passed, violations = validate(result, students, {}, config)
        assert not passed
        assert len(violations) >= 1

    def test_same_row_violation(self):
        """同排同班 — 违规"""
        s1 = Student("S1", "张三", "男", "高三1班", "")
        s2 = Student("S2", "李四", "女", "高三1班", "")
        students = {"S1": s1, "S2": s2}

        result = make_result("A201", 3, 3, [
            (1, 1, "S1"), (1, 3, "S2"),
        ])

        config = ConstraintConfig(isolate_same_class_same_row=True)
        passed, violations = validate(result, students, {}, config)
        assert not passed


class TestRoomCapacity:
    def test_capacity_exceeded(self):
        """超过考场容量"""
        s = Student("S1", "张三", "男", "高三1班", "")
        students = {"S1": s}

        result = make_result("A201", 1, 1, [
            (1, 1, "S1"),
            # 只有1个可用座位但分配了更多（实际上会超出）
        ])
        # 手动超量
        result.classrooms[0].seats.append(SeatAssignment("A201", 1, 1, "S2"))

        config = ConstraintConfig(room_capacity_enabled=True)
        passed, violations = validate(result, students, {}, config)
        # 应该检测到容量违规
        # 注意：两个座位坐标相同，但计数为2，容量为1
        occupied = sum(1 for s in result.classrooms[0].seats if s.student_id is not None)
        capacity = result.classrooms[0].rows * result.classrooms[0].cols
        if occupied > capacity:
            assert not passed
        else:
            # 可能因为座位坐标相同而导致其他检测先触发
            pass


class TestCheaterFront:
    def test_cheater_not_in_front(self):
        s1 = Student("S1", "张三", "男", "高三1班", "", cheating_record="作弊")
        students = {"S1": s1}

        result = make_result("A201", 5, 5, [
            (4, 1, "S1"),  # 第4排 — 不在前2排
        ])

        config = ConstraintConfig(cheater_near_front=True)
        passed, violations = validate(result, students, {}, config)
        assert not passed
        assert any("不在前2排" in v for v in violations)

    def test_cheater_in_front(self):
        s1 = Student("S1", "张三", "男", "高三1班", "", cheating_record="作弊")
        students = {"S1": s1}

        result = make_result("A201", 5, 5, [
            (1, 1, "S1"),  # 第1排
        ])

        config = ConstraintConfig(cheater_near_front=True)
        passed, _ = validate(result, students, {}, config)
        assert passed
