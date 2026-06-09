"""
考场自动排座系统 — Flask 入口

路由：
  GET/POST  /upload           上传 5 CSV + 网格编辑器
  GET/POST  /config           约束配置 + 考试场次配置
  POST      /run              触发排座计算
  GET       /result/classroom 考场维度
  GET       /result/student   考生维度
  GET       /result/teacher   老师维度
  GET       /result/class     班级维度
  GET       /report           评估报告
  GET       /export/json      JSON 导出
  GET       /export/csv       CSV 导出
"""

import json
import uuid
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, Response, send_file,
)
import yaml

from src.models import (
    Student, ClassGroup, Classroom, Subject, Teacher,
    ExamSession, ExamResult, SeatAssignment,
)
from src.io_handler import (
    read_students_csv, read_classes_csv, read_classrooms_csv,
    read_subjects_csv, read_teachers_csv,
    export_to_json, export_to_csv,
    parse_seat_layout, build_seat_layout_str,
)
from src.constraint_engine import ConstraintConfig
from src.sa_solver import SASolver
from src.aco_solver import ACOSolver
from src.evaluator import Evaluator

app = Flask(__name__)
app.secret_key = "kaoshi-fenzuowei-secret-key-change-in-production"

# ═══════════════════════════════════════════════════════════════
# 服务端存储（绕过 Flask session 4KB 限制）
# ═══════════════════════════════════════════════════════════════

_store: dict[str, dict] = {}
"""内存存储: store_id → { students, classes, classrooms, subjects, teachers, results, ... }"""


def _get_store():
    """获取当前 session 的数据存储"""
    sid = session.get("store_id")
    if not sid or sid not in _store:
        sid = str(uuid.uuid4())
        session["store_id"] = sid
        _store[sid] = {}
    return _store[sid]


# ═══════════════════════════════════════════════════════════════
# 班级颜色映射
# ═══════════════════════════════════════════════════════════════

CLASS_COLORS = [
    "#4dc9f6", "#f67019", "#f53794", "#537bc4",
    "#acc236", "#166a8f", "#00a950", "#58595b",
    "#8549ba", "#e6194b", "#3cb44b", "#ffe119",
]

_CLASS_COLOR_MAP: dict[str, str] = {}


def get_class_color(class_id: str) -> str:
    """为班级分配颜色"""
    global _CLASS_COLOR_MAP
    if class_id not in _CLASS_COLOR_MAP:
        idx = len(_CLASS_COLOR_MAP) % len(CLASS_COLORS)
        _CLASS_COLOR_MAP[class_id] = CLASS_COLORS[idx]
    return _CLASS_COLOR_MAP[class_id]


# ═══════════════════════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return redirect(url_for("upload"))


# ── 上传页面 ──────────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
def upload():
    store = _get_store()

    if request.method == "POST":
        action = request.form.get("action", "")

        # CSV 文件上传
        if action == "upload_csvs":
            for csv_type in ["students", "classes", "classrooms", "subjects", "teachers"]:
                file = request.files.get(csv_type)
                if file and file.filename:
                    try:
                        if csv_type == "students":
                            store["students"] = {
                                s.student_id: s for s in read_students_csv(file)
                            }
                        elif csv_type == "classes":
                            store["classes"] = {
                                c.class_id: c for c in read_classes_csv(file)
                            }
                        elif csv_type == "classrooms":
                            store["classrooms"] = {
                                cr.full_room_id: cr for cr in read_classrooms_csv(file)
                            }
                        elif csv_type == "subjects":
                            store["subjects"] = read_subjects_csv(file)
                        elif csv_type == "teachers":
                            store["teachers"] = {
                                t.employee_id: t for t in read_teachers_csv(file)
                            }
                    except Exception as e:
                        return f"解析 {csv_type}.csv 失败: {e}", 400

            return redirect(url_for("upload"))

        # 网格编辑器 — 添加单个考场
        elif action == "add_classroom":
            building = request.form.get("building", "").strip()
            room_id = request.form.get("room_id", "").strip()
            capacity = int(request.form.get("capacity", "0"))
            floor = int(request.form.get("floor", "0"))
            rows = int(request.form.get("rows", "0"))
            cols = int(request.form.get("cols", "0"))
            blocked_str = request.form.get("blocked_seats", "")
            notes = request.form.get("notes", "").strip()

            # 解析阻塞格
            blocked = _parse_blocked_json(blocked_str)

            seat_layout = build_seat_layout_str(rows, cols, blocked)

            cr = Classroom(
                building=building,
                capacity=capacity,
                room_id=room_id,
                floor=floor,
                available=True,
                seat_layout=seat_layout,
                rows=rows,
                cols=cols,
                blocked_seats=blocked,
                notes=notes,
            )

            if "classrooms" not in store:
                store["classrooms"] = {}
            store["classrooms"][cr.full_room_id] = cr

            return redirect(url_for("upload"))

        # 删除考场
        elif action == "delete_classroom":
            rid = request.form.get("room_id", "")
            if "classrooms" in store and rid in store["classrooms"]:
                del store["classrooms"][rid]
            return redirect(url_for("upload"))

    # GET — 汇总当前数据状态
    students = store.get("students", {})
    classes = store.get("classes", {})
    classrooms = store.get("classrooms", {})
    subjects = store.get("subjects", [])
    teachers = store.get("teachers", {})

    return render_template(
        "upload.html",
        student_count=len(students),
        class_count=len(classes),
        classroom_count=len(classrooms),
        subject_count=len(subjects),
        teacher_count=len(teachers),
        classrooms=list(classrooms.values()),
        class_colors=CLASS_COLORS,
    )


# ── 配置页面 ──────────────────────────────────────────────────

@app.route("/config", methods=["GET", "POST"])
def config():
    store = _get_store()

    students = store.get("students", {})
    classrooms = store.get("classrooms", {})
    subjects = store.get("subjects", [])
    teachers = store.get("teachers", {})

    if request.method == "POST":
        # 构建 ConstraintConfig
        cfg = ConstraintConfig(
            isolate_same_class_4adj=request.form.get("isolate_4adj") == "on",
            isolate_same_class_8adj=request.form.get("isolate_8adj") == "on",
            isolate_same_class_same_row=request.form.get("isolate_row") == "on",
            isolate_same_class_same_col=request.form.get("isolate_col") == "on",
            min_gap_same_class=int(request.form.get("min_gap", "0")),
            room_capacity_enabled=request.form.get("capacity_enabled", "on") == "on",
            min_utilization=float(request.form.get("min_utilization", "0")),
            balance_rooms=request.form.get("balance_rooms") == "on",
            cheater_near_front=request.form.get("cheater_front") == "on",
            penalized_near_front=request.form.get("penalized_front") == "on",
            sort_by_student_id=request.form.get("sort_by_id") == "on",
            teacher_one_room=request.form.get("teacher_one_room", "on") == "on",
            teacher_avoid_own_class=request.form.get("teacher_avoid_class") == "on",
            teacher_balance=request.form.get("teacher_balance") == "on",
        )

        # SA 参数
        sa_params = {
            "T_start": float(request.form.get("T_start", "100")),
            "T_end": float(request.form.get("T_end", "0.01")),
            "cooling_rate": float(request.form.get("cooling_rate", "0.9995")),
            "iterations_per_temp": int(request.form.get("iter_per_temp", "100")),
            "restart_count": int(request.form.get("restart_count", "3")),
        }

        # 算法选择
        algorithm = request.form.get("algorithm", "SA")

        # 考试场次配置
        session_subject_codes = request.form.getlist("session_subjects")
        session_datetime = request.form.get("session_datetime", "")

        store["config"] = cfg
        store["sa_params"] = sa_params
        store["algorithm"] = algorithm
        store["session_config"] = {
            "subject_codes": session_subject_codes,
            "datetime": session_datetime,
        }

        return redirect(url_for("run_solver"))

    # 加载默认约束
    default_config = {}
    config_path = Path(__file__).parent / "config" / "default_constraints.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            default_config = yaml.safe_load(f) or {}

    return render_template(
        "config.html",
        students=students,
        classrooms=classrooms,
        subjects=subjects,
        teachers=teachers,
        default_config=default_config,
    )


# ── 运行求解器 ────────────────────────────────────────────────

@app.route("/run", methods=["POST"])
def run_solver():
    store = _get_store()

    students = store.get("students", {})
    classrooms_raw = store.get("classrooms", {})
    subjects = store.get("subjects", [])
    config = store.get("config", ConstraintConfig())
    sa_params = store.get("sa_params", {})
    algorithm = store.get("algorithm", "SA")
    session_cfg = store.get("session_config", {})

    # 构建可用考场列表
    available_classrooms = [
        cr for cr in classrooms_raw.values() if cr.available
    ]
    if not available_classrooms:
        return "没有可用的考场", 400

    # 构建考试场次
    subject_codes = session_cfg.get("subject_codes", [])
    session_datetime = session_cfg.get("datetime", "")

    # 如果没有选择科目，使用所有科目
    selected_subjects = subjects
    if subject_codes:
        selected_subjects = [s for s in subjects if s.code in subject_codes]

    if not selected_subjects:
        return "没有选择考试科目", 400

    # 为每个科目生成场次
    sessions: list[ExamSession] = []
    for subj in selected_subjects:
        # 找出参加该科目的学生
        participant_ids = []
        for sid, student in students.items():
            # 必修科目：同班学生参加
            # 选修科目：elective_subjects 中包含的参加
            if subj.type == "必修" and student.class_id == subj.class_id:
                participant_ids.append(sid)
            elif subj.type == "选修" and subj.name in student.elective_subjects:
                participant_ids.append(sid)
            elif not subj.type:
                # 未指定类型时，包含所有学生
                participant_ids.append(sid)

        session_id = f"{subj.code}_{session_datetime.replace(' ', '_').replace(':', '')}"
        sessions.append(ExamSession(
            session_id=session_id,
            subject=subj,
            datetime=session_datetime,
            student_ids=participant_ids,
        ))

    # 运行求解器
    results: dict[str, ExamResult] = {}

    if algorithm == "ACO":
        solver = ACOSolver(config)
        for session in sessions:
            result = solver.solve(
                session,
                available_classrooms,
                students,
                n_ants=sa_params.get("n_ants", 20),
                n_iterations=sa_params.get("n_iterations", 200),
                evaporation_rate=sa_params.get("evaporation_rate", 0.1),
                alpha=sa_params.get("alpha", 1.0),
                beta=sa_params.get("beta", 2.0),
                timeout_seconds=60.0,
            )
            results[session.session_id] = result
    else:
        solver = SASolver(config)
        for session in sessions:
            result = solver.solve(
                session,
                available_classrooms,
                students,
                T_start=sa_params.get("T_start", 100.0),
                T_end=sa_params.get("T_end", 0.01),
                cooling_rate=sa_params.get("cooling_rate", 0.9995),
                iterations_per_temp=sa_params.get("iterations_per_temp", 100),
                restart_count=sa_params.get("restart_count", 3),
                timeout_seconds=60.0,
            )
            results[session.session_id] = result

    store["results"] = results
    store["energy_history"] = solver.energy_history if hasattr(solver, "energy_history") else []

    # 跳转到第一个结果视图（考场维度）
    return redirect(url_for("result_classroom"))


# ── 结果视图 — 考场维度 ───────────────────────────────────────

@app.route("/result/classroom")
def result_classroom():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})

    # 构建每个考场 × 每个场次的座位矩阵
    view_data = []
    for session_id, result in results.items():
        for cr in result.classrooms:
            # 构建网格
            grid = []
            for r in range(1, cr.rows + 1):
                row_cells = []
                for c in range(1, cr.cols + 1):
                    if (r, c) in cr.blocked:
                        row_cells.append({"type": "blocked", "text": "", "color": "#666"})
                    else:
                        seat = cr.get_seat(r, c)
                        if seat and seat.student_id:
                            s = students.get(seat.student_id)
                            sid_short = ""
                            class_id = ""
                            color = "#ccc"
                            cheating = False
                            penalty = 0
                            name = ""
                            if s:
                                sid_short = s.student_id[-3:] if len(s.student_id) >= 3 else s.student_id
                                class_id = s.class_id
                                color = get_class_color(s.class_id)
                                cheating = s.has_cheating_record
                                penalty = s.penalty
                                name = s.name
                            row_cells.append({
                                "type": "occupied",
                                "text": sid_short,
                                "color": color,
                                "student_id": seat.student_id,
                                "name": name,
                                "class_id": class_id,
                                "cheating": cheating,
                                "penalty": penalty,
                                "row": r,
                                "col": c,
                            })
                        else:
                            row_cells.append({"type": "empty", "text": "—", "color": "#e8e8e8"})
                grid.append(row_cells)

            view_data.append({
                "session_id": session_id,
                "session_label": f"{result.session.subject.name} {result.session.datetime}",
                "room_id": cr.room_id,
                "rows": cr.rows,
                "cols": cr.cols,
                "grid": grid,
                "occupied": cr.occupied_count,
                "available": cr.available_count,
            })

    # 收集班级颜色映射
    class_colors = {}
    all_class_ids = set()
    for s in students.values():
        all_class_ids.add(s.class_id)
    for cid in sorted(all_class_ids):
        class_colors[cid] = get_class_color(cid)

    return render_template(
        "result_classroom.html",
        view_data=view_data,
        class_colors=class_colors,
    )


# ── 结果视图 — 考生维度 ───────────────────────────────────────

@app.route("/result/student")
def result_student():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})

    # 构建每个学生的考试卡片
    student_records: dict[str, dict] = {}
    for sid, s in students.items():
        student_records[sid] = {
            "student": s,
            "color": get_class_color(s.class_id),
            "exams": [],
        }

    for session_id, result in results.items():
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id and seat.student_id in student_records:
                    student_records[seat.student_id]["exams"].append({
                        "subject": result.session.subject.name,
                        "datetime": result.session.datetime,
                        "room_id": cr.room_id,
                        "row": seat.row,
                        "col": seat.col,
                        "building": cr.room_id[0] if cr.room_id else "",
                    })

    return render_template(
        "result_student.html",
        student_records=student_records,
        get_class_color=get_class_color,
    )


# ── 结果视图 — 老师维度 ───────────────────────────────────────

@app.route("/result/teacher")
def result_teacher():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    teachers: dict[str, Teacher] = store.get("teachers", {})
    students: dict[str, Student] = store.get("students", {})
    config: ConstraintConfig = store.get("config", ConstraintConfig())

    # 简单监考分配：为每个考场分配一位有监考资格的老师
    # 收集所有考场
    all_rooms: set[str] = set()
    for result in results.values():
        for cr in result.classrooms:
            all_rooms.add(cr.room_id)

    qualified_teachers = [
        t for t in teachers.values() if t.invigilation_qualified
    ]

    # 按考场分配
    invigilation: list[dict] = []
    teacher_idx = 0
    for room_id in sorted(all_rooms):
        if teacher_idx < len(qualified_teachers):
            teacher = qualified_teachers[teacher_idx]
        else:
            teacher = None
        teacher_idx += 1

        # 找出这个考场中涉及的班级
        room_classes: set[str] = set()
        for result in results.values():
            for cr in result.classrooms:
                if cr.room_id == room_id:
                    for seat in cr.seats:
                        if seat.student_id and seat.student_id in students:
                            room_classes.add(students[seat.student_id].class_id)

        # 检测冲突
        conflict = False
        if config.teacher_avoid_own_class and teacher:
            # 老师任教科目的班级
            teacher_class = ""
            for subj in store.get("subjects", []):
                if subj.teacher_name == teacher.name:
                    teacher_class = subj.class_id
            if teacher_class in room_classes:
                conflict = True

        invigilation.append({
            "room_id": room_id,
            "teacher_name": teacher.name if teacher else "未分配",
            "teacher_subject": teacher.subject if teacher else "",
            "classes": list(room_classes),
            "conflict": conflict,
        })

    return render_template(
        "result_teacher.html",
        invigilation=invigilation,
        sessions=list(results.keys()),
    )


# ── 结果视图 — 班级维度 ───────────────────────────────────────

@app.route("/result/class")
def result_class():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})

    # 统计每个班级在每个考场的分布
    class_distribution: dict[str, dict[str, int]] = {}  # class_id → {room_id → count}

    for result in results.values():
        for cr in result.classrooms:
            for seat in cr.seats:
                if seat.student_id and seat.student_id in students:
                    cid = students[seat.student_id].class_id
                    if cid not in class_distribution:
                        class_distribution[cid] = {}
                    class_distribution[cid][cr.room_id] = class_distribution[cid].get(cr.room_id, 0) + 1

    # 收集所有考场
    all_rooms: list[str] = sorted(set(
        cr.room_id for result in results.values() for cr in result.classrooms
    ))

    # 构建 Chart.js 数据
    chart_labels = all_rooms
    chart_datasets = []
    for cid in sorted(class_distribution.keys()):
        dist = class_distribution[cid]
        chart_datasets.append({
            "label": cid,
            "data": [dist.get(room, 0) for room in all_rooms],
            "backgroundColor": get_class_color(cid),
        })

    # 热力图数据：每个考场的每个座位属于哪个班级
    heatmap_data = []
    selected_class = request.args.get("class_id", "")
    if selected_class:
        for result in results.values():
            for cr in result.classrooms:
                grid = []
                for r in range(1, cr.rows + 1):
                    row_data = []
                    for c in range(1, cr.cols + 1):
                        if (r, c) in cr.blocked:
                            row_data.append({"type": "blocked"})
                        else:
                            seat = cr.get_seat(r, c)
                            if seat and seat.student_id and seat.student_id in students:
                                s = students[seat.student_id]
                                is_highlight = (s.class_id == selected_class)
                                row_data.append({
                                    "type": "occupied",
                                    "highlight": is_highlight,
                                    "class_id": s.class_id,
                                })
                            else:
                                row_data.append({"type": "empty"})
                    grid.append(row_data)
                heatmap_data.append({
                    "session_id": result.session.session_id,
                    "session_label": f"{result.session.subject.name}",
                    "room_id": cr.room_id,
                    "grid": grid,
                })

    return render_template(
        "result_class.html",
        class_distribution=class_distribution,
        all_rooms=all_rooms,
        chart_labels=chart_labels,
        chart_datasets=chart_datasets,
        heatmap_data=heatmap_data,
        selected_class=selected_class,
        class_ids=sorted(class_distribution.keys()),
        get_class_color=get_class_color,
    )


# ── 评估报告 ──────────────────────────────────────────────────

@app.route("/report")
def report():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})
    config: ConstraintConfig = store.get("config", ConstraintConfig())
    energy_history: list[float] = store.get("energy_history", [])

    evaluator = Evaluator()
    reports = {}
    for session_id, result in results.items():
        reports[session_id] = evaluator.evaluate(result, students, config, energy_history)

    return render_template(
        "report.html",
        reports=reports,
        results=results,
    )


# ── 导出 ──────────────────────────────────────────────────────

@app.route("/export/json")
def export_json():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})

    all_data = {}
    for session_id, result in results.items():
        all_data[session_id] = json.loads(export_to_json(result, students))

    return Response(
        json.dumps(all_data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=exam_seating.json"},
    )


@app.route("/export/csv")
def export_csv():
    store = _get_store()
    results: dict[str, ExamResult] = store.get("results", {})
    students: dict[str, Student] = store.get("students", {})

    all_csv_parts = []
    for session_id, result in results.items():
        all_csv_parts.append(export_to_csv(result, students))

    combined = "\n".join(all_csv_parts)
    return Response(
        combined,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=exam_seating.csv"},
    )


# ── 辅助 ──────────────────────────────────────────────────────

def _parse_blocked_json(blocked_str: str) -> list[tuple[int, int]]:
    """解析前端传来的阻塞格 JSON"""
    if not blocked_str:
        return []
    try:
        data = json.loads(blocked_str)
        return [tuple(pair) for pair in data]
    except (json.JSONDecodeError, TypeError):
        return []


# ═══════════════════════════════════════════════════════════════
# 模板辅助函数
# ═══════════════════════════════════════════════════════════════

@app.context_processor
def utility_processor():
    return {
        "get_class_color": get_class_color,
        "CLASS_COLORS": CLASS_COLORS,
    }


# ═══════════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
