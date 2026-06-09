"""测试数据模型"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    Student, ClassGroup, Classroom, Subject, Teacher,
    ExamSession, SeatAssignment, ClassroomResult, ExamResult,
)


class TestStudent:
    def test_has_cheating_record(self):
        s1 = Student("S1001", "张三", "男", "高三1班", "A101", cheating_record="夹带纸条")
        s2 = Student("S1002", "李四", "女", "高三1班", "A102", cheating_record="")
        assert s1.has_cheating_record
        assert not s2.has_cheating_record

    def test_has_penalty(self):
        s1 = Student("S1001", "张三", "男", "高三1班", "A101", penalty=5)
        s2 = Student("S1002", "李四", "女", "高三1班", "A102", penalty=0)
        assert s1.has_penalty
        assert not s2.has_penalty

    def test_elective_subjects_default(self):
        s = Student("S1001", "张三", "男", "高三1班", "A101")
        assert s.elective_subjects == []


class TestClassroom:
    def test_full_room_id(self):
        cr = Classroom("A", 48, "201", 2)
        assert cr.full_room_id == "A201"

    def test_available_seats_count(self):
        cr = Classroom("B", 30, "105", 1, rows=6, cols=5, blocked_seats=[(3, 3)])
        assert cr.available_seats_count == 29  # 30 - 1

    def test_utilization(self):
        cr = Classroom("A", 48, "201", 2, rows=8, cols=6)
        assert cr.utilization == 1.0

        cr2 = Classroom("A", 100, "201", 2, rows=8, cols=6)
        assert cr2.utilization == 48.0 / 100.0


class TestExamResult:
    def test_find_student(self):
        session = ExamSession("TEST", Subject("数学", "MATH"), "2025-01-20 08:00")
        seat = SeatAssignment("A201", 1, 1, "S1001")
        cr = ClassroomResult("A201", 8, 6, seats=[seat])
        result = ExamResult(session, classrooms=[cr])

        found = result.find_student("S1001")
        assert len(found) == 1
        assert found[0][1].student_id == "S1001"

    def test_find_student_not_found(self):
        session = ExamSession("TEST", Subject("数学", "MATH"))
        result = ExamResult(session, classrooms=[])
        found = result.find_student("S9999")
        assert len(found) == 0
