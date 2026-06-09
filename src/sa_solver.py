"""
模拟退火求解器 (Simulated Annealing Solver)

核心流程：
  1. 初始化：随机分配学生到可用座位
  2. 目标函数 energy(result)：硬约束违规 × 1000 + 空座 × 1 + 软约束惩罚
  3. 邻域扰动：交换/移动/跨考场互换
  4. Metropolis 接受准则
  5. 退火计划 + 重启机制
"""

import math
import random
import time
from copy import deepcopy

from .models import (
    ExamSession, Classroom, Student, ExamResult, ClassroomResult,
    SeatAssignment,
)
from .constraint_engine import ConstraintConfig, count_violations, compute_balance_penalty
from .seat_graph import SeatGraph


class SASolver:
    """
    模拟退火排座求解器。

    初始化 → 多轮降温 × 多次重启 → 返回最优方案。
    每次迭代记录 energy 值，支持超时中断返回当前最优。
    """

    def __init__(self, config: ConstraintConfig):
        self.config = config
        self._energy_history: list[float] = []

    @property
    def name(self) -> str:
        return "Simulated Annealing"

    @property
    def energy_history(self) -> list[float]:
        return self._energy_history

    def solve(
        self,
        session,
        classrooms: list[Classroom],
        students: dict[str, Student],
        *,
        T_start: float = 100.0,
        T_end: float = 0.01,
        cooling_rate: float = 0.9995,
        iterations_per_temp: int = 100,
        restart_count: int = 3,
        timeout_seconds: float = 60.0,
    ) -> ExamResult:
        """
        执行模拟退火求解。

        Args:
            session: 考试场次
            classrooms: 可用考场列表
            students: 学号 → Student（只分配 session.student_ids 中的学生）
            T_start: 初始温度
            T_end: 终止温度
            cooling_rate: 冷却速率
            iterations_per_temp: 每个温度下的迭代次数
            restart_count: 退火重启次数
            timeout_seconds: 最大运行时间（秒），超时返回当前最优

        Returns:
            ExamResult 包含最优排座方案
        """
        self._energy_history = []

        # 确定参与学生
        participant_ids = list(session.student_ids) if session.student_ids else list(students.keys())
        participants = {sid: students[sid] for sid in participant_ids if sid in students}

        # 过滤可用考场
        available_rooms = [c for c in classrooms if c.available and c.rows > 0 and c.cols > 0]
        if not available_rooms:
            raise ValueError("没有可用的考场")

        # 构建邻接图
        adjacency_mode = "eight" if self.config.isolate_same_class_8adj else "four"
        seat_graph = SeatGraph(available_rooms, adjacency_mode=adjacency_mode)

        start_time = time.time()
        best_result: ExamResult | None = None
        best_energy = float('inf')

        for restart in range(restart_count):
            if time.time() - start_time > timeout_seconds:
                break

            # 初始化随机分配
            current_result = self._random_init(session, available_rooms, participants, seat_graph)
            current_energy = self._energy(current_result, participants, seat_graph)

            T = T_start
            iteration = 0
            steps_since_improvement = 0

            while T > T_end:
                if time.time() - start_time > timeout_seconds:
                    break

                for _ in range(iterations_per_temp):
                    iteration += 1

                    # 邻域扰动
                    new_result = self._perturb(current_result, participants, seat_graph)
                    new_energy = self._energy(new_result, participants, seat_graph)

                    # Metropolis 接受准则
                    delta = new_energy - current_energy
                    if delta < 0 or random.random() < math.exp(-delta / T):
                        current_result = new_result
                        current_energy = new_energy

                        if current_energy < best_energy:
                            best_energy = current_energy
                            best_result = deepcopy(current_result)
                            steps_since_improvement = 0

                    self._energy_history.append(current_energy)

                steps_since_improvement += 1
                T *= cooling_rate

                # 早停：如果长时间无改进
                if steps_since_improvement > 500 and T < 1.0:
                    break

        # 如果从未改进，返回最后结果
        if best_result is None:
            best_result = current_result

        elapsed = time.time() - start_time
        best_result.metadata = {
            "algorithm": self.name,
            "iterations": len(self._energy_history),
            "time_elapsed": round(elapsed, 2),
            "final_energy": best_energy,
            "restart_count": restart_count,
            "T_start": T_start,
            "T_end": T_end,
            "cooling_rate": cooling_rate,
        }

        # 确保座位在每个考场内按 row, col 排序
        for cr in best_result.classrooms:
            cr.seats.sort(key=lambda s: (s.row, s.col))

        return best_result

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    def _random_init(
        self,
        session,
        classrooms: list[Classroom],
        participants: dict[str, Student],
        seat_graph: SeatGraph,
    ) -> ExamResult:
        """随机初始化：将所有学生随机分配到可用座位"""
        # 收集所有可用座位
        all_seats: list[tuple[str, int, int]] = []  # (room_id, row, col)
        for cr in classrooms:
            for r in range(1, cr.rows + 1):
                for c in range(1, cr.cols + 1):
                    if (r, c) not in cr.blocked_seats:
                        all_seats.append((cr.full_room_id, r, c))

        if len(all_seats) < len(participants):
            raise ValueError(
                f"可用座位 ({len(all_seats)}) 少于考生人数 ({len(participants)})"
            )

        # 随机打乱座位
        random.shuffle(all_seats)

        # 分配学生
        student_ids = list(participants.keys())
        random.shuffle(student_ids)

        # 构建 ClassroomResult
        room_results: dict[str, ClassroomResult] = {}
        for cr in classrooms:
            room_results[cr.full_room_id] = ClassroomResult(
                room_id=cr.full_room_id,
                rows=cr.rows,
                cols=cr.cols,
                blocked=list(cr.blocked_seats),
                seats=[],
            )

        for i, (room_id, r, c) in enumerate(all_seats):
            sid = student_ids[i] if i < len(student_ids) else None
            seat = SeatAssignment(room_id=room_id, row=r, col=c, student_id=sid)
            room_results[room_id].seats.append(seat)

        return ExamResult(
            session=session,
            classrooms=list(room_results.values()),
        )

    def _energy(
        self,
        result: ExamResult,
        participants: dict[str, Student],
        seat_graph: SeatGraph,
    ) -> float:
        """
        目标函数：越低越好。

        = 硬约束违规数 × 1000 + 空座位数 × 1 + 均衡惩罚 × 10
        """
        violations = count_violations(result, participants, self.config, seat_graph)
        # 空座位数
        empty_count = 0
        for cr in result.classrooms:
            empty_count += sum(1 for s in cr.seats if s.student_id is None)

        energy = violations * 1000.0 + empty_count * 1.0

        # 软约束：均衡惩罚
        if self.config.balance_rooms:
            balance = compute_balance_penalty(result)
            energy += balance * 10.0

        return energy

    def _perturb(
        self,
        result: ExamResult,
        participants: dict[str, Student],
        seat_graph: SeatGraph,
    ) -> ExamResult:
        """
        邻域扰动：随机选择一种扰动并返回新方案。

        策略：
          a. 交换两个已占座位的学生 (90%)
          b. 将一个学生移到空座 (8%)
          c. 跨考场互换两个学生 (2%)
        """
        new_result = deepcopy(result)

        # 收集所有座位信息
        all_seats: list[SeatAssignment] = []
        for cr in new_result.classrooms:
            all_seats.extend(cr.seats)

        occupied = [(i, s) for i, s in enumerate(all_seats) if s.student_id is not None]
        empty = [(i, s) for i, s in enumerate(all_seats) if s.student_id is None]

        r = random.random()

        if r < 0.90 and len(occupied) >= 2:
            # a. 交换两个已占座位
            i1, s1 = random.choice(occupied)
            i2, s2 = random.choice(occupied)
            while i2 == i1:
                i2, s2 = random.choice(occupied)
            s1.student_id, s2.student_id = s2.student_id, s1.student_id

        elif r < 0.98 and empty and occupied:
            # b. 将一个学生移到空座
            _, src = random.choice(occupied)
            _, dst = random.choice(empty)
            dst.student_id = src.student_id
            src.student_id = None

        else:
            # c. 跨考场互换
            # 找两个不同考场的已占座位
            room_seats: dict[str, list[SeatAssignment]] = {}
            for cr in new_result.classrooms:
                room_seats[cr.room_id] = [s for s in cr.seats if s.student_id is not None]

            rooms_with_occupied = [rid for rid, seats in room_seats.items() if seats]
            if len(rooms_with_occupied) >= 2:
                r1 = random.choice(rooms_with_occupied)
                r2 = random.choice(rooms_with_occupied)
                attempts = 0
                while r2 == r1 and attempts < 10:
                    r2 = random.choice(rooms_with_occupied)
                    attempts += 1

                if r1 != r2:
                    s1 = random.choice(room_seats[r1])
                    s2 = random.choice(room_seats[r2])
                    s1.student_id, s2.student_id = s2.student_id, s1.student_id

        return new_result

    def _get_seat_by_coord(self, result: ExamResult, room_id: str, row: int, col: int):
        """根据坐标获取座位对象"""
        for cr in result.classrooms:
            if cr.room_id == room_id:
                for seat in cr.seats:
                    if seat.row == row and seat.col == col:
                        return seat
        return None
