"""
蚁群算法求解器 (Ant Colony Optimization Solver)

核心思路：
  信息素矩阵 tau[student_idx][seat_idx] — 该学生放在该座位上的"好感度"

每轮迭代：
  1. N 只蚂蚁各自独立构建排座方案（按信息素+启发式概率选择）
  2. 评估每只蚂蚁的方案
  3. 信息素蒸发 + 精英蚂蚁强化
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


class ACOSolver:
    """
    蚁群算法排座求解器。

    信息素矩阵大小: N_students × N_seats
    每只蚂蚁独立建解 → 评估 → 更新信息素
    """

    def __init__(self, config: ConstraintConfig):
        self.config = config
        self._energy_history: list[float] = []

    @property
    def name(self) -> str:
        return "Ant Colony Optimization"

    @property
    def energy_history(self) -> list[float]:
        return self._energy_history

    def solve(
        self,
        session,
        classrooms: list[Classroom],
        students: dict[str, Student],
        *,
        n_ants: int = 20,
        n_iterations: int = 200,
        evaporation_rate: float = 0.1,
        alpha: float = 1.0,
        beta: float = 2.0,
        timeout_seconds: float = 60.0,
    ) -> ExamResult:
        """
        执行蚁群算法求解。

        Args:
            session: 考试场次
            classrooms: 可用考场列表
            students: 学号 → Student
            n_ants: 蚂蚁数量
            n_iterations: 迭代轮数
            evaporation_rate: 信息素蒸发率 ρ
            alpha: 信息素权重
            beta: 启发式权重
            timeout_seconds: 超时秒数

        Returns:
            ExamResult
        """
        self._energy_history = []

        # 确定参与学生
        participant_ids = list(session.student_ids) if session.student_ids else list(students.keys())
        participants: dict[str, Student] = {
            sid: students[sid] for sid in participant_ids if sid in students
        }
        student_list = list(participants.keys())  # 保持索引顺序
        n_students = len(student_list)

        # 过滤可用考场
        available_rooms = [c for c in classrooms if c.available and c.rows > 0 and c.cols > 0]
        if not available_rooms:
            raise ValueError("没有可用的考场")

        # 收集所有可用座位
        all_seats: list[tuple[str, int, int]] = []  # (room_id, row, col)
        for cr in available_rooms:
            for r in range(1, cr.rows + 1):
                for c in range(1, cr.cols + 1):
                    if (r, c) not in cr.blocked_seats:
                        all_seats.append((cr.full_room_id, r, c))

        n_seats = len(all_seats)
        if n_seats < n_students:
            raise ValueError(f"可用座位 ({n_seats}) 少于考生人数 ({n_students})")

        # 构建邻接图
        adjacency_mode = "eight" if self.config.isolate_same_class_8adj else "four"
        seat_graph = SeatGraph(available_rooms, adjacency_mode=adjacency_mode)

        # 初始化信息素矩阵 — 均匀分布
        tau0 = 1.0 / n_seats
        tau: list[list[float]] = [
            [tau0 for _ in range(n_seats)] for _ in range(n_students)
        ]

        # 启发式因子矩阵 η[i][j] — 基于历史偏好（初始为 1）
        eta: list[list[float]] = [
            [1.0 for _ in range(n_seats)] for _ in range(n_students)
        ]

        start_time = time.time()
        best_result: ExamResult | None = None
        best_energy = float('inf')

        for iteration in range(n_iterations):
            if time.time() - start_time > timeout_seconds:
                break

            # 每只蚂蚁构建方案
            ant_results: list[tuple[ExamResult, float]] = []
            for _ in range(n_ants):
                result = self._construct_solution(
                    session, available_rooms, student_list, all_seats,
                    tau, eta, alpha, beta, seat_graph,
                )
                energy = self._energy(result, participants, seat_graph)
                ant_results.append((result, energy))
                self._energy_history.append(energy)

                if energy < best_energy:
                    best_energy = energy
                    best_result = deepcopy(result)

            # 信息素蒸发
            for i in range(n_students):
                for j in range(n_seats):
                    tau[i][j] *= (1.0 - evaporation_rate)

            # 精英蚂蚁强化 — 本轮最优
            ant_results.sort(key=lambda x: x[1])
            best_ant_result, best_ant_energy = ant_results[0]
            deposit = 1.0 / max(best_ant_energy, 1e-6)

            for cr in best_ant_result.classrooms:
                for seat in cr.seats:
                    if seat.student_id:
                        try:
                            si = student_list.index(seat.student_id)
                            seat_idx = self._find_seat_index(
                                all_seats, cr.room_id, seat.row, seat.col
                            )
                            if seat_idx >= 0:
                                tau[si][seat_idx] += deposit
                        except ValueError:
                            pass

        if best_result is None:
            best_result = self._construct_solution(
                session, available_rooms, student_list, all_seats,
                tau, eta, alpha, beta, seat_graph,
            )

        elapsed = time.time() - start_time
        best_result.metadata = {
            "algorithm": self.name,
            "iterations": len(self._energy_history),
            "time_elapsed": round(elapsed, 2),
            "final_energy": best_energy,
            "n_ants": n_ants,
            "n_iterations": n_iterations,
            "evaporation_rate": evaporation_rate,
        }

        # 排序
        for cr in best_result.classrooms:
            cr.seats.sort(key=lambda s: (s.row, s.col))

        return best_result

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    def _construct_solution(
        self,
        session,
        classrooms: list[Classroom],
        student_list: list[str],
        all_seats: list[tuple[str, int, int]],
        tau: list[list[float]],
        eta: list[list[float]],
        alpha: float,
        beta: float,
        seat_graph: SeatGraph,
    ) -> ExamResult:
        """单只蚂蚁构建排座方案"""
        n_students = len(student_list)
        n_seats = len(all_seats)

        # 可用座位索引（未被分配的）
        available_indices = list(range(n_seats))
        random.shuffle(available_indices)

        # 学生分配映射: seat_idx → student_id
        assignment: dict[int, str] = {}

        # 随机顺序处理学生
        remaining_students = list(range(n_students))
        random.shuffle(remaining_students)

        for si in remaining_students:
            # 计算每个可用座位的选择概率
            if not available_indices:
                break

            probs = []
            for seat_idx in available_indices:
                p = (tau[si][seat_idx] ** alpha) * (eta[si][seat_idx] ** beta)
                probs.append(p)

            total = sum(probs)
            if total == 0:
                # 均匀随机选
                chosen = random.choice(available_indices)
            else:
                # 轮盘赌选择
                r = random.random() * total
                cumulative = 0.0
                chosen = available_indices[0]
                for idx, p in zip(available_indices, probs):
                    cumulative += p
                    if cumulative >= r:
                        chosen = idx
                        break

            assignment[chosen] = student_list[si]
            available_indices.remove(chosen)

        # 构建 ExamResult
        room_results: dict[str, ClassroomResult] = {}
        for cr in classrooms:
            room_results[cr.full_room_id] = ClassroomResult(
                room_id=cr.full_room_id,
                rows=cr.rows,
                cols=cr.cols,
                blocked=list(cr.blocked_seats),
                seats=[],
            )

        for seat_idx, (room_id, r, c) in enumerate(all_seats):
            sid = assignment.get(seat_idx)
            seat = SeatAssignment(room_id=room_id, row=r, col=c, student_id=sid)
            room_results[room_id].seats.append(seat)

        return ExamResult(
            session=session,
            classrooms=list(room_results.values()),
        )

    def _find_seat_index(
        self,
        all_seats: list[tuple[str, int, int]],
        room_id: str,
        row: int,
        col: int,
    ) -> int:
        """根据 room_id, row, col 查找座位索引"""
        for i, (rid, r, c) in enumerate(all_seats):
            if rid == room_id and r == row and c == col:
                return i
        return -1

    def _energy(
        self,
        result: ExamResult,
        participants: dict[str, Student],
        seat_graph: SeatGraph,
    ) -> float:
        """目标函数"""
        violations = count_violations(result, participants, self.config, seat_graph)
        empty_count = sum(
            sum(1 for s in cr.seats if s.student_id is None)
            for cr in result.classrooms
        )
        energy = violations * 1000.0 + empty_count * 1.0
        if self.config.balance_rooms:
            energy += compute_balance_penalty(result) * 10.0
        return energy
