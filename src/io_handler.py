"""
IO 处理器 — CSV/JSON 读写、seat_layout 解析、导出。

数据流向：
  CSV 上传 → pandas DataFrame → dataclass 列表 → 内存存储
  结果 → 扁平化 DataFrame → JSON/CSV 导出
"""

import csv
import io
import json
from typing import Optional

import pandas as pd

from .models import (
    Student, ClassGroup, Classroom, Subject, Teacher,
    ExamResult, SeatAssignment
)


# ═══════════════════════════════════════════════════════════════
# seat_layout 解析
# ═══════════════════════════════════════════════════════════════

def parse_seat_layout(layout_str: str) -> tuple[int, int, list[tuple[int, int]]]:
    """
    解析 seat_layout 字符串。

    格式：
      "8×6"              → 8 行 6 列，无阻塞
      "8×6!(4,1);(8,6)"  → 8 行 6 列，(4,1) 和 (8,6) 不可用

    Returns:
        (rows, cols, blocked_seats) — blocked_seats 为 1-indexed 坐标列表
    """
    if not layout_str or not layout_str.strip():
        return 0, 0, []

    layout_str = layout_str.strip()

    # 按 ! 分割
    if '!' in layout_str:
        grid_part, blocked_part = layout_str.split('!', 1)
    else:
        grid_part = layout_str
        blocked_part = ""

    # 解析 rows×cols
    if '×' in grid_part:
        rows_str, cols_str = grid_part.split('×', 1)
    elif 'x' in grid_part:
        rows_str, cols_str = grid_part.split('x', 1)
    else:
        raise ValueError(f"Invalid seat_layout format: '{layout_str}' — expected 'rows×cols'")

    rows = int(rows_str.strip())
    cols = int(cols_str.strip())

    # 解析阻塞坐标
    blocked_seats: list[tuple[int, int]] = []
    if blocked_part:
        # 按 ; 分割
        for coord_str in blocked_part.split(';'):
            coord_str = coord_str.strip()
            if not coord_str:
                continue
            # 去掉括号
            coord_str = coord_str.strip('()（）')
            if ',' in coord_str:
                r_str, c_str = coord_str.split(',', 1)
            else:
                raise ValueError(f"Invalid blocked coord: '{coord_str}'")
            r, c = int(r_str.strip()), int(c_str.strip())
            # 校验坐标
            if r < 1 or r > rows or c < 1 or c > cols:
                raise ValueError(
                    f"Blocked seat ({r},{c}) out of bounds for {rows}×{cols} grid"
                )
            blocked_seats.append((r, c))

    return rows, cols, blocked_seats


def build_seat_layout_str(rows: int, cols: int, blocked_seats: list[tuple[int, int]]) -> str:
    """反向构建 seat_layout 字符串。"""
    if not blocked_seats:
        return f"{rows}×{cols}"
    blocked_str = ";".join(f"({r},{c})" for r, c in blocked_seats)
    return f"{rows}×{cols}!{blocked_str}"


# ═══════════════════════════════════════════════════════════════
# CSV 读取
# ═══════════════════════════════════════════════════════════════

def _read_csv_safe(filepath_or_buffer, encoding='utf-8-sig') -> pd.DataFrame:
    """安全读取 CSV，自动处理编码和空文件。"""
    try:
        return pd.read_csv(filepath_or_buffer, encoding=encoding, dtype=str)
    except Exception:
        # 尝试其他编码
        return pd.read_csv(filepath_or_buffer, encoding='utf-8', dtype=str)


def read_students_csv(filepath_or_buffer) -> list[Student]:
    """
    读取 students.csv → list[Student]。

    必需列: student_id, name, gender, class_id
    可选列: dormitory, elective_subjects, cheating_record, penalty, id_number, contact, notes
    """
    df = _read_csv_safe(filepath_or_buffer)
    students = []
    for _, row in df.iterrows():
        elective_str = str(row.get('elective_subjects', ''))
        elective_list = []
        if elective_str and elective_str not in ('nan', 'None', ''):
            elective_list = [s.strip() for s in elective_str.split(';') if s.strip()]

        penalty_val = row.get('penalty', '0')
        try:
            penalty = int(float(penalty_val)) if penalty_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            penalty = 0

        students.append(Student(
            student_id=str(row.get('student_id', '')).strip(),
            name=str(row.get('name', '')).strip(),
            gender=str(row.get('gender', '')).strip(),
            class_id=str(row.get('class_id', '')).strip(),
            dormitory=str(row.get('dormitory', '')).strip(),
            elective_subjects=elective_list,
            cheating_record=str(row.get('cheating_record', '')).strip(),
            penalty=penalty,
            id_number=str(row.get('id_number', '')).strip(),
            contact=str(row.get('contact', '')).strip(),
            notes=str(row.get('notes', '')).strip(),
        ))
    return students


def read_classes_csv(filepath_or_buffer) -> list[ClassGroup]:
    """读取 classes.csv → list[ClassGroup]"""
    df = _read_csv_safe(filepath_or_buffer)
    classes = []
    for _, row in df.iterrows():
        count_val = row.get('student_count', '0')
        try:
            count = int(float(count_val)) if count_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            count = 0

        classes.append(ClassGroup(
            class_id=str(row.get('class_id', '')).strip(),
            student_count=count,
            advisor=str(row.get('advisor', '')).strip(),
            major=str(row.get('major', '')).strip(),
            grade=str(row.get('grade', '')).strip(),
            classroom_id=str(row.get('classroom_id', '')).strip(),
            notes=str(row.get('notes', '')).strip(),
        ))
    return classes


def read_classrooms_csv(filepath_or_buffer) -> list[Classroom]:
    """读取 classrooms.csv → list[Classroom]，自动解析 seat_layout"""
    df = _read_csv_safe(filepath_or_buffer)
    classrooms = []
    for _, row in df.iterrows():
        capacity_val = row.get('capacity', '0')
        try:
            capacity = int(float(capacity_val)) if capacity_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            capacity = 0

        floor_val = row.get('floor', '0')
        try:
            floor = int(float(floor_val)) if floor_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            floor = 0

        available_str = str(row.get('available', '是')).strip()
        available = available_str not in ('否', 'False', 'false', '0', 'No', 'no')

        layout_str = str(row.get('seat_layout', ''))
        if layout_str in ('nan', 'None', ''):
            layout_str = ""

        # 解析 seat_layout
        if layout_str:
            rows, cols, blocked = parse_seat_layout(layout_str)
        else:
            rows, cols, blocked = 0, 0, []

        classrooms.append(Classroom(
            building=str(row.get('building', '')).strip(),
            capacity=capacity,
            room_id=str(row.get('room_id', '')).strip(),
            floor=floor,
            available=available,
            seat_layout=layout_str,
            notes=str(row.get('notes', '')).strip(),
            rows=rows,
            cols=cols,
            blocked_seats=blocked,
        ))
    return classrooms


def read_subjects_csv(filepath_or_buffer) -> list[Subject]:
    """读取 subjects.csv → list[Subject]"""
    df = _read_csv_safe(filepath_or_buffer)
    subjects = []
    for _, row in df.iterrows():
        dur_val = row.get('duration_minutes', '0')
        try:
            dur = int(float(dur_val)) if dur_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            dur = 0

        cap_val = row.get('room_capacity', '0')
        try:
            cap = int(float(cap_val)) if cap_val not in ('nan', 'None', '') else 0
        except (ValueError, TypeError):
            cap = 0

        subjects.append(Subject(
            name=str(row.get('name', '')).strip(),
            code=str(row.get('code', '')).strip(),
            type=str(row.get('type', '')).strip(),
            class_id=str(row.get('class_id', '')).strip(),
            teacher_name=str(row.get('teacher_name', '')).strip(),
            duration_minutes=dur,
            room_capacity=cap,
            notes=str(row.get('notes', '')).strip(),
        ))
    return subjects


def read_teachers_csv(filepath_or_buffer) -> list[Teacher]:
    """读取 teachers.csv → list[Teacher]"""
    df = _read_csv_safe(filepath_or_buffer)
    teachers = []
    for _, row in df.iterrows():
        qual_str = str(row.get('invigilation_qualified', '否')).strip()
        qualified = qual_str in ('是', 'True', 'true', '1', 'Yes', 'yes')

        teachers.append(Teacher(
            employee_id=str(row.get('employee_id', '')).strip(),
            name=str(row.get('name', '')).strip(),
            gender=str(row.get('gender', '')).strip(),
            subject=str(row.get('subject', '')).strip(),
            phone=str(row.get('phone', '')).strip(),
            invigilation_qualified=qualified,
            title=str(row.get('title', '')).strip(),
            notes=str(row.get('notes', '')).strip(),
        ))
    return teachers


# ═══════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════

def export_to_json(result: ExamResult, students: dict[str, Student]) -> str:
    """
    导出完整 ExamResult 为 JSON 字符串。

    结构：
    {
      "session": { ... },
      "classrooms": [ { "room_id": ..., "seats": [ ... ] } ],
      "metadata": { ... }
    }
    """
    def _serialize(obj):
        """递归序列化 dataclass → dict"""
        if hasattr(obj, '__dataclass_fields__'):
            result_dict = {}
            for f_name in obj.__dataclass_fields__:
                val = getattr(obj, f_name)
                result_dict[f_name] = _serialize(val)
            return result_dict
        elif isinstance(obj, list):
            return [_serialize(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        elif isinstance(obj, tuple):
            return list(obj)
        else:
            return obj

    output = {
        "session": _serialize(result.session),
        "classrooms": _serialize(result.classrooms),
        "metadata": _serialize(result.metadata),
    }

    # 为学生座位补充姓名和班级信息
    for cr in output["classrooms"]:
        for seat in cr.get("seats", []):
            sid = seat.get("student_id")
            if sid and sid in students:
                s = students[sid]
                seat["student_name"] = s.name
                seat["class_id"] = s.class_id
                seat["cheating_record"] = s.cheating_record
                seat["penalty"] = s.penalty
            else:
                seat["student_name"] = ""
                seat["class_id"] = ""
                seat["cheating_record"] = ""
                seat["penalty"] = 0

    return json.dumps(output, ensure_ascii=False, indent=2)


def export_to_csv(result: ExamResult, students: dict[str, Student]) -> str:
    """
    导出为扁平化 CSV 字符串。

    列: session, subject, room, building, row, col, student_id, name, class_id,
         cheating_record, penalty
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # 表头
    writer.writerow([
        "session", "subject", "room", "building", "row", "col",
        "student_id", "name", "class_id", "cheating_record", "penalty"
    ])

    session_id = result.session.session_id
    subject_name = result.session.subject.name

    for cr in result.classrooms:
        # 从 room_id 提取 building（如 "A201" → "A"）
        building = _extract_building(cr.room_id)

        for seat in cr.seats:
            if seat.student_id and seat.student_id in students:
                s = students[seat.student_id]
                writer.writerow([
                    session_id, subject_name,
                    cr.room_id, building,
                    seat.row, seat.col,
                    seat.student_id, s.name, s.class_id,
                    s.cheating_record, s.penalty
                ])
            else:
                writer.writerow([
                    session_id, subject_name,
                    cr.room_id, building,
                    seat.row, seat.col,
                    "", "", "",
                    "", 0
                ])

    return output.getvalue()


def _extract_building(room_id: str) -> str:
    """从 room_id 提取 building 字母前缀，如 'A201' → 'A'"""
    building = ""
    for ch in room_id:
        if ch.isalpha():
            building += ch
        else:
            break
    return building
