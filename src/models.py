"""
数据模型 — 考场自动排座系统的所有数据类。

对应 data/ 目录下 CSV 文件的列头：
  Student → students.csv
  ClassGroup → classes.csv
  Classroom → classrooms.csv
  Subject → subjects.csv
  Teacher → teachers.csv
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Student:
    """Student — corresponds to data/students.csv"""
    student_id: str              # 学号，唯一标识
    name: str                    # 姓名
    gender: str                  # 性别（男/女）
    class_id: str                # 班级（如 "高三1班"），一个学生只属于一个班级
    dormitory: str               # 寝室
    elective_subjects: list[str] = field(default_factory=list)  # 选修科目
    cheating_record: str = ""    # 作弊记录（空字符串表示无记录）
    penalty: int = 0             # 扣分（0 表示无扣分）
    id_number: str = ""          # 身份证号
    contact: str = ""            # 联系方式（手机号）
    notes: str = ""              # 备注

    @property
    def has_cheating_record(self) -> bool:
        return bool(self.cheating_record and self.cheating_record.strip())

    @property
    def has_penalty(self) -> bool:
        return self.penalty > 0


@dataclass
class ClassGroup:
    """ClassGroup — corresponds to data/classes.csv"""
    class_id: str                # 班级名，如 "高三1班"
    student_count: int = 0       # 人数
    advisor: str = ""            # 辅导员
    major: str = ""              # 专业
    grade: str = ""              # 年级
    classroom_id: str = ""       # 教室编号
    notes: str = ""              # 备注


@dataclass
class Classroom:
    """Classroom — corresponds to data/classrooms.csv"""
    building: str                # 楼号，如 "A", "B", "C"
    capacity: int                # 容量（最大容纳人数）
    room_id: str                 # 教室编号，如 "201" 或 "C201"
    floor: int                   # 楼层
    available: bool = True       # 是否可用
    seat_layout: str = ""        # 座位布局，如 "8×6" 或 "8×6!(4,1);(8,6)"
    notes: str = ""              # 备注
    # 以下为从 seat_layout 解析出的派生字段：
    rows: int = 0
    cols: int = 0
    blocked_seats: list[tuple[int, int]] = field(default_factory=list)

    @property
    def full_room_id(self) -> str:
        """返回楼号+教室编号，如 'A201'"""
        return f"{self.building}{self.room_id}"

    @property
    def available_seats_count(self) -> int:
        """可用座位数 = 总座位 - 阻塞格"""
        total = self.rows * self.cols
        return total - len(self.blocked_seats)

    @property
    def utilization(self) -> float:
        """利用率 = 可用座位 / capacity"""
        if self.capacity == 0:
            return 0.0
        return self.available_seats_count / self.capacity


@dataclass
class Subject:
    """Subject — corresponds to data/subjects.csv"""
    name: str                    # 科目名字（如 "数学"）
    code: str                    # 科目编号（如 "MATH"）
    type: str = ""               # 类型（如 "必修", "选修"）
    class_id: str = ""           # 所属班级
    teacher_name: str = ""       # 任课教师姓名
    duration_minutes: int = 0    # 考试时长（分钟）
    room_capacity: int = 0       # 该科目考场容量
    notes: str = ""              # 备注


@dataclass
class Teacher:
    """Teacher — corresponds to data/teachers.csv"""
    employee_id: str             # 职工号
    name: str                    # 名字
    gender: str = ""             # 性别
    subject: str = ""            # 任教科目
    phone: str = ""              # 手机号
    invigilation_qualified: bool = False  # 监考资格（是/否 → True/False）
    title: str = ""              # 职称
    notes: str = ""              # 备注


@dataclass
class ExamSession:
    """考试场次 — 由用户在 Web 页面从已上传的科目中选择"""
    session_id: str              # 场次ID，如 "MATH_20250120_AM"
    subject: Subject             # 科目对象（引用）
    datetime: str = ""           # 考试时间，如 "2025-01-20 08:00-10:00"
    student_ids: list[str] = field(default_factory=list)  # 参加该科目的学生学号集合


@dataclass
class SeatAssignment:
    """单个座位的分配信息"""
    room_id: str
    row: int                     # 1-indexed
    col: int                     # 1-indexed
    student_id: Optional[str] = None  # None = 空座


@dataclass
class ClassroomResult:
    """单个考场的排座结果"""
    room_id: str
    rows: int
    cols: int
    blocked: list[tuple[int, int]] = field(default_factory=list)
    seats: list[SeatAssignment] = field(default_factory=list)

    def get_seat(self, row: int, col: int) -> Optional[SeatAssignment]:
        """根据行列获取座位"""
        for seat in self.seats:
            if seat.row == row and seat.col == col:
                return seat
        return None

    def is_blocked(self, row: int, col: int) -> bool:
        return (row, col) in self.blocked

    @property
    def occupied_count(self) -> int:
        return sum(1 for s in self.seats if s.student_id is not None)

    @property
    def available_count(self) -> int:
        return self.rows * self.cols - len(self.blocked)


@dataclass
class ExamResult:
    """单场考试的完整排座结果"""
    session: ExamSession
    classrooms: list[ClassroomResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # metadata 示例: { "algorithm": "SA", "iterations": 5000, "time_elapsed": 12.3 }

    def get_all_seats(self) -> list[SeatAssignment]:
        """获取所有座位分配"""
        result = []
        for cr in self.classrooms:
            result.extend(cr.seats)
        return result

    def find_student(self, student_id: str) -> list[tuple[ClassroomResult, SeatAssignment]]:
        """查找某学生在哪些考场、哪些座位"""
        found = []
        for cr in self.classrooms:
            for seat in cr.seats:
                if seat.student_id == student_id:
                    found.append((cr, seat))
        return found
