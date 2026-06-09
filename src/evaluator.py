"""
评估器 — 生成排座方案的评估报告。

指标：
  - 收敛曲线 (energy history)
  - 约束满足率
  - 考场利用率
  - 班级隔离度
  - 运算耗时
"""

from dataclasses import dataclass, field

from .models import ExamResult, Student
from .constraint_engine import ConstraintConfig, validate, count_violations
from .seat_graph import SeatGraph


@dataclass
class EvaluationReport:
    """评估报告"""

    energy_curve: list[float] = field(default_factory=list)
    constraint_pass_rate: float = 0.0       # 0~1
    room_utilization: dict[str, float] = field(default_factory=dict)  # room_id → 利用率
    class_isolation_score: float = 0.0       # 0~1，越高越好 → 1 - (同班相邻对数 / 总相邻对)
    time_elapsed: float = 0.0
    total_violations: int = 0
    violation_details: list[str] = field(default_factory=list)


class Evaluator:
    """
    评估器 — 对 ExamResult 进行全面评估。

    用法:
        evaluator = Evaluator()
        report = evaluator.evaluate(result, students, config, energy_history)
    """

    def evaluate(
        self,
        result: ExamResult,
        students: dict[str, Student],
        config: ConstraintConfig,
        energy_history: list[float] | None = None,
    ) -> EvaluationReport:
        """
        生成评估报告。

        Args:
            result: 排座结果
            students: 学号 → Student
            config: 约束配置
            energy_history: 算法迭代的 energy 序列

        Returns:
            EvaluationReport
        """
        report = EvaluationReport()

        # 收敛曲线
        if energy_history:
            report.energy_curve = list(energy_history)
        else:
            report.energy_curve = []

        # 约束满足率
        passed, violations = validate(result, students, {}, config)
        report.violation_details = violations
        report.total_violations = len(violations)

        # 计算违规总数作为满足率的反向指标
        hard_violations = [v for v in violations if "建议" not in v]
        # 硬约束总数估算（与实际配置有关）
        total_checks = self._estimate_total_checks(result)
        if total_checks > 0:
            report.constraint_pass_rate = max(0.0, 1.0 - len(hard_violations) / total_checks)
        else:
            report.constraint_pass_rate = 1.0

        # 考场利用率
        for cr in result.classrooms:
            occupied = sum(1 for s in cr.seats if s.student_id is not None)
            capacity = cr.rows * cr.cols - len(cr.blocked)
            if capacity > 0:
                report.room_utilization[cr.room_id] = occupied / capacity
            else:
                report.room_utilization[cr.room_id] = 0.0

        # 班级隔离度 — 计算同班相邻对数
        report.class_isolation_score = self._compute_isolation_score(result, students)

        # 耗时
        report.time_elapsed = result.metadata.get("time_elapsed", 0.0)

        return report

    def _estimate_total_checks(self, result: ExamResult) -> int:
        """估算检查总数（用于满足率分母）"""
        total = 0
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id:
                    total += 1  # 每个学生至少有一次检查
        return max(1, total)

    def _compute_isolation_score(
        self,
        result: ExamResult,
        students: dict[str, Student],
    ) -> float:
        """
        计算班级隔离度分数。

        分数 = 1 - (同班相邻对数 / 总相邻座位对)
        越高越好。

        使用四邻模式计算。
        """
        # 构建临时的 SeatGraph (四邻)
        total_adjacent_pairs = 0
        same_class_pairs = 0

        for cr in result.classrooms:
            # 构建座位 → 学生映射
            seat_student: dict[tuple[int, int], Student] = {}
            for seat in cr.seats:
                if seat.student_id and seat.student_id in students:
                    seat_student[(seat.row, seat.col)] = students[seat.student_id]

            # 四邻检测
            checked: set[tuple[tuple[int, int], tuple[int, int]]] = set()
            for (r, c), s1 in seat_student.items():
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    pair = ((r, c), (nr, nc))
                    rev_pair = ((nr, nc), (r, c))
                    if pair in checked or rev_pair in checked:
                        continue

                    s2 = seat_student.get((nr, nc))
                    if s2 is not None:
                        checked.add(pair)
                        total_adjacent_pairs += 1
                        if s1.class_id == s2.class_id:
                            same_class_pairs += 1

        if total_adjacent_pairs == 0:
            return 1.0

        return 1.0 - (same_class_pairs / total_adjacent_pairs)
