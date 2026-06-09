"""
约束引擎 — 约束配置与违规检测。

支持硬约束（违反方案无效）和软约束（作为优化目标惩罚项）。

硬约束：
  - 班级隔离（四邻/八邻/同排/同列/最小间隔）
  - 考场容量上限
  - 最低利用率
  - 作弊/扣分考生前排

软约束：
  - 考场人数均衡 (balance_rooms)
  - 监考工作量均衡 (teacher_balance)
"""

from dataclasses import dataclass, field

from .models import ExamResult, Student, ClassGroup, ClassroomResult, Teacher
from .seat_graph import SeatGraph


@dataclass
class ConstraintConfig:
    """约束配置 — 对应 Web 页面的勾选项"""

    # 班级隔离
    isolate_same_class_4adj: bool = True     # 四邻无同班
    isolate_same_class_8adj: bool = False    # 八邻无同班
    isolate_same_class_same_row: bool = False  # 同排无同班
    isolate_same_class_same_col: bool = False  # 同列无同班
    min_gap_same_class: int = 0              # 同班最少间隔座位数（0=不限制）

    # 考场管理
    room_capacity_enabled: bool = True       # 考场容量上限
    min_utilization: float = 0.0             # 最低利用率（0~1）
    balance_rooms: bool = False              # 各考场人数尽量均衡（软约束）

    # 学生分配
    cheater_near_front: bool = False         # 有作弊记录的学生优先安排在前排
    penalized_near_front: bool = False       # 有扣分记录的学生优先安排在前排
    sort_by_student_id: bool = False         # 同考场内按学号排列

    # 监考分配
    teacher_one_room: bool = True            # 一位监考只负责一个考场
    teacher_avoid_own_class: bool = False    # 监考不监考自己任教的班级
    teacher_balance: bool = False            # 监考工作量均衡（软约束）


def validate(
    result: ExamResult,
    students: dict[str, Student],
    class_groups: dict[str, ClassGroup],
    config: ConstraintConfig,
    seat_graph: SeatGraph | None = None,
) -> tuple[bool, list[str]]:
    """
    校验排座方案是否满足所有硬约束。

    Args:
        result: 排座结果
        students: 学号 → Student
        class_groups: 班级ID → ClassGroup（当前未使用，预留）
        config: 约束配置
        seat_graph: 邻接图（用于邻接检测）。如果为 None 则自动构建。

    Returns:
        (是否通过, 违规描述列表)
    """
    violations: list[str] = []

    # 如果需要邻接检测但没有提供 seat_graph，自动构建
    if seat_graph is None and (
        config.isolate_same_class_4adj
        or config.isolate_same_class_8adj
    ):
        from .models import Classroom

        # 从结果中重建 Classroom 列表
        classrooms = []
        for cr in result.classrooms:
            c = Classroom(
                building="",
                capacity=cr.available_count,
                room_id=cr.room_id,
                floor=0,
                available=True,
                rows=cr.rows,
                cols=cr.cols,
                blocked_seats=cr.blocked,
            )
            classrooms.append(c)

        adjacency_mode = "eight" if config.isolate_same_class_8adj else "four"
        seat_graph = SeatGraph(classrooms, adjacency_mode=adjacency_mode)

    # 1. 班级隔离 — 四邻
    if config.isolate_same_class_4adj:
        _check_adjacency_isolation(result, students, seat_graph, "four", violations)

    # 2. 班级隔离 — 八邻
    if config.isolate_same_class_8adj:
        _check_adjacency_isolation(result, students, seat_graph, "eight", violations)

    # 3. 班级隔离 — 同排
    if config.isolate_same_class_same_row:
        _check_row_isolation(result, students, violations)

    # 4. 班级隔离 — 同列
    if config.isolate_same_class_same_col:
        _check_col_isolation(result, students, violations)

    # 5. 最小间隔
    if config.min_gap_same_class > 0:
        _check_min_gap(result, students, config.min_gap_same_class, violations)

    # 6. 考场容量
    if config.room_capacity_enabled:
        _check_room_capacity(result, violations)

    # 7. 最低利用率（这里只标记，不算硬违规）
    if config.min_utilization > 0:
        _check_utilization(result, config.min_utilization, violations)

    # 8. 作弊考生前排
    if config.cheater_near_front:
        _check_cheater_front(result, students, "cheating", violations)

    # 9. 扣分考生前排
    if config.penalized_near_front:
        _check_cheater_front(result, students, "penalty", violations)

    return len(violations) == 0, violations


# ═══════════════════════════════════════════════════════════════
# 各约束检查子函数
# ═══════════════════════════════════════════════════════════════

def _check_adjacency_isolation(
    result: ExamResult,
    students: dict[str, Student],
    seat_graph: SeatGraph | None,
    mode: str,
    violations: list[str],
):
    """检查邻接（四邻/八邻）同班隔离"""
    if seat_graph is None:
        return

    for cr in result.classrooms:
        room = seat_graph.get_room(cr.room_id)
        if room is None:
            continue

        # 构建座位 → student 映射
        seat_student: dict[tuple[int, int], Student] = {}
        for seat in cr.seats:
            if seat.student_id and seat.student_id in students:
                seat_student[(seat.row, seat.col)] = students[seat.student_id]

        for (r, c), s1 in seat_student.items():
            for nr, nc in room.get_neighbors(r, c):
                s2 = seat_student.get((nr, nc))
                if s2 is not None and s1.class_id == s2.class_id:
                    violations.append(
                        f"{cr.room_id} 考场: 座位({r},{c})的 {s1.student_id}({s1.class_id}) "
                        f"与 座位({nr},{nc})的 {s2.student_id}({s2.class_id}) 相邻({mode}邻)"
                    )


def _check_row_isolation(
    result: ExamResult,
    students: dict[str, Student],
    violations: list[str],
):
    """检查同排同班隔离"""
    for cr in result.classrooms:
        for row in range(1, cr.rows + 1):
            row_seats = [s for s in cr.seats if s.row == row and s.student_id]
            class_ids_in_row: dict[str, list[str]] = {}
            for seat in row_seats:
                sid = seat.student_id
                if sid and sid in students:
                    cid = students[sid].class_id
                    class_ids_in_row.setdefault(cid, []).append(sid)

            for cid, student_ids in class_ids_in_row.items():
                if len(student_ids) >= 2:
                    violations.append(
                        f"{cr.room_id} 考场: 第{row}排出现 {len(student_ids)} 名 "
                        f"{cid} 学生: {', '.join(student_ids)}"
                    )


def _check_col_isolation(
    result: ExamResult,
    students: dict[str, Student],
    violations: list[str],
):
    """检查同列同班隔离"""
    for cr in result.classrooms:
        for col in range(1, cr.cols + 1):
            col_seats = [s for s in cr.seats if s.col == col and s.student_id]
            class_ids_in_col: dict[str, list[str]] = {}
            for seat in col_seats:
                sid = seat.student_id
                if sid and sid in students:
                    cid = students[sid].class_id
                    class_ids_in_col.setdefault(cid, []).append(sid)

            for cid, student_ids in class_ids_in_col.items():
                if len(student_ids) >= 2:
                    violations.append(
                        f"{cr.room_id} 考场: 第{col}列出现 {len(student_ids)} 名 "
                        f"{cid} 学生: {', '.join(student_ids)}"
                    )


def _check_min_gap(
    result: ExamResult,
    students: dict[str, Student],
    min_gap: int,
    violations: list[str],
):
    """检查同班最小间隔"""
    for cr in result.classrooms:
        # 收集每个班级的学生在哪些座位上
        class_seats: dict[str, list[tuple[int, int, str]]] = {}
        for seat in cr.seats:
            if seat.student_id and seat.student_id in students:
                cid = students[seat.student_id].class_id
                class_seats.setdefault(cid, []).append((seat.row, seat.col, seat.student_id))

        for cid, seat_list in class_seats.items():
            for i in range(len(seat_list)):
                r1, c1, sid1 = seat_list[i]
                for j in range(i + 1, len(seat_list)):
                    r2, c2, sid2 = seat_list[j]
                    # 棋盘距离
                    gap = max(abs(r1 - r2), abs(c1 - c2))
                    if gap < min_gap:
                        violations.append(
                            f"{cr.room_id} 考场: {cid}的 {sid1}({r1},{c1}) 与 "
                            f"{sid2}({r2},{c2}) 间隔={gap} < {min_gap}"
                        )


def _check_room_capacity(result: ExamResult, violations: list[str]):
    """检查考场容量"""
    for cr in result.classrooms:
        occupied = sum(1 for s in cr.seats if s.student_id is not None)
        capacity = cr.rows * cr.cols - len(cr.blocked)
        if occupied > capacity:
            violations.append(
                f"{cr.room_id} 考场: 已用 {occupied} > 容量 {capacity}"
            )


def _check_utilization(result: ExamResult, min_util: float, violations: list[str]):
    """检查最低利用率（标记为建议不开，不算硬违规）"""
    for cr in result.classrooms:
        occupied = sum(1 for s in cr.seats if s.student_id is not None)
        capacity = cr.rows * cr.cols - len(cr.blocked)
        if capacity == 0:
            continue
        util = occupied / capacity
        if util < min_util:
            violations.append(
                f"{cr.room_id} 考场: 利用率 {util:.1%} < {min_util:.0%}，建议不开"
            )


def _check_cheater_front(
    result: ExamResult,
    students: dict[str, Student],
    check_type: str,
    violations: list[str],
):
    """
    检查作弊/扣分考生是否在前 2 排。

    Args:
        check_type: "cheating" (作弊记录) 或 "penalty" (扣分)
    """
    for cr in result.classrooms:
        for seat in cr.seats:
            if seat.student_id and seat.student_id in students:
                s = students[seat.student_id]
                is_target = False
                if check_type == "cheating" and s.has_cheating_record:
                    is_target = True
                elif check_type == "penalty" and s.has_penalty:
                    is_target = True

                if is_target and seat.row > 2:
                    label = "作弊记录" if check_type == "cheating" else "扣分"
                    violations.append(
                        f"{cr.room_id} 考场: {s.student_id}({s.name})有{label} "
                        f"但座位在第{seat.row}排，不在前2排"
                    )


# ═══════════════════════════════════════════════════════════════
# 辅助：计算违规数量（供算法目标函数使用）
# ═══════════════════════════════════════════════════════════════

def count_violations(
    result: ExamResult,
    students: dict[str, Student],
    config: ConstraintConfig,
    seat_graph: SeatGraph | None = None,
) -> int:
    """
    快速计算硬约束违规数量（用于算法 energy 函数）。
    只计数，不生成详细描述。
    """
    count = 0

    if seat_graph is None:
        from .models import Classroom
        classrooms = []
        for cr in result.classrooms:
            c = Classroom(
                building="", capacity=cr.available_count,
                room_id=cr.room_id, floor=0, available=True,
                rows=cr.rows, cols=cr.cols, blocked_seats=cr.blocked,
            )
            classrooms.append(c)
        adjacency_mode = "eight" if config.isolate_same_class_8adj else "four"
        seat_graph = SeatGraph(classrooms, adjacency_mode=adjacency_mode)

    # 四邻同班隔离
    if config.isolate_same_class_4adj or config.isolate_same_class_8adj:
        mode = "eight" if config.isolate_same_class_8adj else "four"
        for cr in result.classrooms:
            room = seat_graph.get_room(cr.room_id)
            if room is None:
                continue
            seat_student = {}
            for seat in cr.seats:
                if seat.student_id and seat.student_id in students:
                    seat_student[(seat.row, seat.col)] = students[seat.student_id]
            checked: set[tuple[tuple[int, int], tuple[int, int]]] = set()
            for (r, c), s1 in seat_student.items():
                for nr, nc in room.get_neighbors(r, c):
                    s2 = seat_student.get((nr, nc))
                    pair = ((r, c), (nr, nc))
                    rev_pair = ((nr, nc), (r, c))
                    if s2 is not None and s1.class_id == s2.class_id:
                        if pair not in checked and rev_pair not in checked:
                            checked.add(pair)
                            count += 1

    # 同排隔离
    if config.isolate_same_class_same_row:
        for cr in result.classrooms:
            for row in range(1, cr.rows + 1):
                class_count: dict[str, int] = {}
                for seat in cr.seats:
                    if seat.row == row and seat.student_id and seat.student_id in students:
                        cid = students[seat.student_id].class_id
                        class_count[cid] = class_count.get(cid, 0) + 1
                for c, n in class_count.items():
                    if n >= 2:
                        count += n - 1

    # 同列隔离
    if config.isolate_same_class_same_col:
        for cr in result.classrooms:
            for col in range(1, cr.cols + 1):
                class_count: dict[str, int] = {}
                for seat in cr.seats:
                    if seat.col == col and seat.student_id and seat.student_id in students:
                        cid = students[seat.student_id].class_id
                        class_count[cid] = class_count.get(cid, 0) + 1
                for c, n in class_count.items():
                    if n >= 2:
                        count += n - 1

    # 考场容量
    if config.room_capacity_enabled:
        for cr in result.classrooms:
            occupied = sum(1 for s in cr.seats if s.student_id is not None)
            capacity = cr.rows * cr.cols - len(cr.blocked)
            if occupied > capacity:
                count += occupied - capacity

    # 作弊前排
    if config.cheater_near_front:
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id and seat.student_id in students:
                    s = students[seat.student_id]
                    if s.has_cheating_record and seat.row > 2:
                        count += 1

    # 扣分前排
    if config.penalized_near_front:
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id and seat.student_id in students:
                    s = students[seat.student_id]
                    if s.has_penalty and seat.row > 2:
                        count += 1

    return count


def compute_balance_penalty(result: ExamResult) -> float:
    """
    计算考场人数不均衡的软约束惩罚值。

    返回各考场人数的标准差（越小越均衡）。
    """
    counts = []
    for cr in result.classrooms:
        occupied = sum(1 for s in cr.seats if s.student_id is not None)
        counts.append(occupied)

    if not counts:
        return 0.0

    mean = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    return variance ** 0.5
