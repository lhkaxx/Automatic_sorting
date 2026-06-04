---
name: kaoshifenzuowei
description: 考场自动排座系统全栈规范——基于模拟退火/蚁群算法的期末考场排座 Web 应用。覆盖数据模型、算法、约束引擎、Flask 后端、4 维度可视化、导出、测试与文档。
---

# 考场自动排座系统 — 全栈开发规范

## 一、项目概览

### 1.1 技术栈（不可更改）
| 层 | 技术 | 备注 |
|---|---|---|
| 后端框架 | **Flask** | 服务端渲染模板，不引入前端框架 |
| 模板引擎 | **Jinja2** | Flask 自带 |
| 前端增强 | **原生 JS + Chart.js** | 仅用于交互增强、座位图渲染、图表；禁止引入 React/Vue |
| 数据处理 | **pandas + numpy** | CSV/Excel 读写、矩阵运算 |
| 算法 | **手写实现** | 模拟退火 (SA) 为主，蚁群算法 (ACO) 为可选对比；禁止调包 |
| 存储 | **内存 + JSON/CSV 导出** | 无需数据库；结果在 session 内保持，支持下载 |

### 1.2 项目结构（必须遵循）
```
kaoshifenzuowei/
├── app.py                     # Flask 入口
├── requirements.txt
├── config/
│   └── default_constraints.yaml
├── src/
│   ├── __init__.py
│   ├── models.py              # 所有数据类
│   ├── io_handler.py          # 5-CSV read/write (students/classes/classrooms/subjects/teachers), seat_layout parser, JSON/CSV export
│   ├── seat_graph.py          # 邻接图构建（网格 + 阻塞格）
│   ├── constraint_engine.py   # 约束校验
│   ├── algorithm_base.py      # 算法抽象基类
│   ├── sa_solver.py           # 模拟退火
│   ├── aco_solver.py          # 蚁群算法（可选）
│   └── evaluator.py           # 评估报告
├── templates/
│   ├── base.html
│   ├── upload.html
│   ├── config.html
│   ├── result_classroom.html
│   ├── result_student.html
│   ├── result_teacher.html
│   ├── result_class.html
│   └── report.html
├── static/
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_models.py
│   ├── test_seat_graph.py
│   ├── test_constraint_engine.py
│   ├── test_sa_solver.py
│   ├── test_aco_solver.py
│   └── test_integration.py
├── data/
│   ├── students.csv
│   ├── classes.csv
│   ├── classrooms.csv
│   ├── subjects.csv
│   └── teachers.csv
└── docs/
    ├── ALGORITHM.md
    ├── API.md
    └── USER_GUIDE.md
```

---

## 二、数据模型（`src/models.py`）

### 2.1 必须实现的数据类（Python dataclass）

> **数据来源**：以下字段与 `data/` 目录下的 CSV 列头一一对应。
> Student → `students.csv` | ClassGroup → `classes.csv` | Classroom → `classrooms.csv` | Subject → `subjects.csv` | Teacher → `teachers.csv`

```python
@dataclass
class Student:
    """Student — corresponds to data/students.csv"""
    student_id: str        # 学号，唯一标识
    name: str              # 姓名
    gender: str            # 性别（男/女）
    class_id: str          # 班级（如 "高三1班"），一个学生只属于一个班级
    dormitory: str         # 寝室
    elective_subjects: list[str]  # 选修科目（分号分隔 → 解析为列表）
    cheating_record: str   # 作弊记录（空字符串表示无记录）
    penalty: int           # 扣分（0 表示无扣分）
    id_number: str         # 身份证号
    contact: str           # 联系方式（手机号）
    notes: str             # 备注

@dataclass
class ClassGroup:
    """ClassGroup — corresponds to data/classes.csv"""
    class_id: str          # 班级名，如 "高三1班"
    student_count: int     # 人数
    advisor: str           # 辅导员
    major: str             # 专业
    grade: str             # 年级
    classroom_id: str      # 教室编号
    notes: str             # 备注

@dataclass
class Classroom:
    """Classroom — corresponds to data/classrooms.csv"""
    building: str          # 楼号，如 "A", "B", "C"
    capacity: int          # 容量（最大容纳人数）
    room_id: str           # 教室编号，如 "201" 或 "C201"
    floor: int             # 楼层
    available: bool        # 是否可用
    seat_layout: str       # 座位布局，如 "8×6"（行×列），含阻塞格时扩展为 "8×6!(4,1);(8,6)"
    # 以下为从 seat_layout 解析出的派生字段：
    rows: int              # 行数（解析自 seat_layout）
    cols: int              # 列数（解析自 seat_layout）
    blocked_seats: list[tuple[int, int]]  # 阻塞座位坐标 (row, col)，1-indexed（解析自 seat_layout）
    notes: str             # 备注

@dataclass
class Subject:
    """Subject — corresponds to data/subjects.csv"""
    name: str              # 科目名字（如 "数学"）
    code: str              # 科目编号（如 "MATH"）
    type: str              # 类型（如 "必修", "选修"）
    class_id: str          # 所属班级
    teacher_name: str      # 任课教师姓名
    duration_minutes: int  # 考试时长（分钟）
    room_capacity: int     # 该科目考场容量
    notes: str             # 备注

@dataclass
class Teacher:
    """Teacher — corresponds to data/teachers.csv"""
    employee_id: str       # 职工号
    name: str              # 名字
    gender: str            # 性别
    subject: str           # 任教科目
    phone: str             # 手机号
    invigilation_qualified: bool  # 监考资格（是/否 → True/False）
    title: str             # 职称
    notes: str             # 备注

@dataclass
class ExamSession:
    """考试场次 — 由用户在 Web 页面从已上传的科目中选择"""
    session_id: str        # 场次ID，如 "MATH_20250120_AM"
    subject: Subject       # 科目对象（引用）
    datetime: str          # 考试时间，如 "2025-01-20 08:00-10:00"
    student_ids: list[str] # 参加该科目的学生学号集合

@dataclass
class SeatAssignment:
    room_id: str
    row: int               # 1-indexed
    col: int               # 1-indexed
    student_id: str | None # None = 空座

@dataclass
class ClassroomResult:
    room_id: str
    rows: int
    cols: int
    blocked: list[tuple[int, int]]
    seats: list[SeatAssignment]

@dataclass
class ExamResult:
    session: ExamSession
    classrooms: list[ClassroomResult]
    metadata: dict         # { "algorithm": "SA", "iterations": 5000, "time_elapsed": 12.3 }
```

### 2.2 考场座位模型核心规则

**统一模型：所有考场最终都是「网格 + 阻塞格」**

- 规则矩形考场：`rows × cols`，`blocked_seats` 为空或极少
- 不规则考场：通过标记 `blocked_seats` 来"挖掉"不存在的座位区域（比如阶梯教室弧形边缘、实验室操作台占位）
- **数据来源**：`classrooms.csv` 的 `seat_layout` 列。格式为 `{rows}×{cols}`，可选追加 `!{blocked coords}`：
  - 纯网格：`8×6` → 8 行 6 列，无阻塞
  - 含阻塞：`8×6!(4,1);(8,6)` → 8 行 6 列，第 (4,1) 和 (8,6) 不可用
- **解析逻辑**（`src/io_handler.py` 中实现 `parse_seat_layout(layout_str: str) -> tuple[int, int, list[tuple[int,int]]]`）：
  1. 按 `!` 分割：`[rows×cols, blocked_part]`
  2. 解析 `rows×cols` 得到 int rows, cols
  3. 如果存在 blocked_part，按 `;` 分割，逐个解析 `(row,col)` → `tuple[int,int]`
  4. 校验坐标不越界，校验 rows × cols 与 capacity 一致性

```
示例：5×6 考场，后排缺角

列→ 1 2 3 4 5 6
行1  □ □ □ □ □ □
行2  □ □ □ □ □ □
行3  □ □ □ □ □ □
行4  □ □ □ ■ ■ ■   ← blocked: (4,4), (4,5), (4,6)
行5  □ □ □ ■ ■ ■   ← blocked: (5,4), (5,5), (5,6)

seat_layout string: "5×6!(4,4);(4,5);(4,6);(5,4);(5,5);(5,6)"
可用座位 = 5×6 - 6 = 24
```

**阻塞格由用户在 Web 上传时指定**——上传页面提供两种方式：
1. **CSV 直接上传**：`classrooms.csv` 的 `seat_layout` 列包含阻塞信息（推荐批量导入）
2. **网格编辑器**（逐个考场微调）：
   1. 用户输入 rows 和 cols
   2. 页面渲染一个 `rows × cols` 的网格
   3. 用户点击格子切换"可用/阻塞"状态
   4. 点击过的格子坐标保存为 `blocked_seats`
   5. 自动生成 `seat_layout` 字符串写入 `Classroom.seat_layout`

---

## 三、邻接图构建（`src/seat_graph.py`）

### 3.1 核心类

```python
class SeatGraph:
    """将网格 + 阻塞格 转换为邻接图，供约束引擎高效查询"""
    rooms: dict[str, RoomGraph]

class RoomGraph:
    room_id: str
    available_seats: list[tuple[int, int]]        # 所有可用座位坐标
    adjacency: dict[tuple[int,int], list[tuple[int,int]]]  # 邻接表
```

### 3.2 邻接规则

两个可用座位 `(r1,c1)` 与 `(r2,c2)` 相邻：

- **四邻**：`|r1-r2| + |c1-c2| == 1`
- **八邻**：`max(|r1-r2|, |c1-c2|) == 1`

必须支持两种模式，由约束勾选决定用哪一种。

### 3.3 构建算法

```
1. 收集所有 available_seats = (r,c) 且 (r,c) NOT IN blocked_seats
2. 对每个 available_seat:
    遍历其四邻/八邻方向
    如果邻居也在 available_seats 中 → 加入邻接表
```

---

## 四、约束引擎（`src/constraint_engine.py`）

### 4.1 约束配置

所有约束通过一个 `ConstraintConfig` 对象控制，该对象由 Web 页面的勾选项构造：

```python
@dataclass
class ConstraintConfig:
    # 班级隔离
    isolate_same_class_4adj: bool = True    # 四邻无同班
    isolate_same_class_8adj: bool = False   # 八邻无同班
    isolate_same_class_same_row: bool = False  # 同排无同班
    isolate_same_class_same_col: bool = False  # 同列无同班
    min_gap_same_class: int = 0             # 同班最少间隔座位数（0=不限制）

    # 考场管理
    room_capacity_enabled: bool = True      # 考场容量上限
    min_utilization: float = 0.0            # 最低利用率（0~1）
    balance_rooms: bool = False             # 各考场人数尽量均衡（软约束）

    # 学生分配（判别来源：Student.cheating_record, Student.penalty）
    cheater_near_front: bool = False        # 有作弊记录的学生优先安排在前排
    penalized_near_front: bool = False      # 有扣分记录的学生优先安排在前排
    sort_by_student_id: bool = False        # 同考场内按学号排列

    # 监考分配（依赖 data/teachers.csv）
    teacher_one_room: bool = True           # 一位监考只负责一个考场
    teacher_avoid_own_class: bool = False   # 监考不监考自己任教的班级
    teacher_balance: bool = False           # 监考工作量均衡（软约束）
```

### 4.2 约束校验方法签名

```python
def validate(
    result: ExamResult,
    students: dict[str, Student],
    class_groups: dict[str, ClassGroup],
    config: ConstraintConfig
) -> tuple[bool, list[str]]:
    """
    返回 (是否通过, 违规描述列表)
    违规描述示例: "C201 考场: 座位(3,2)的 S1001(高三1班) 与 座位(3,3)的 S1002(高三1班) 相邻(四邻)"
    """
```

### 4.3 校验规则具体实现要求

**四邻/八邻同班隔离**：
```
遍历每个考场每个座位 (r,c):
  如果该座位有学生 s1(班级 c1):
    遍历该座位的邻接表中所有座位 (nr,nc):
      如果有学生 s2(班级 c1) → 违规
```

**同排/同列隔离**：
```
遍历每个考场每排/每列:
  统计该排/列中各班出现的次数
  如果某班出现 ≥2 次 → 违规
```

**考场容量**：
```
每个教室的学生数 ≤ rows × cols - len(blocked_seats)
```

**最低利用率**：
```
考场已用座位数 / 可用座位数 ≥ min_utilization
如果配置了 min_utilization > 0，低于阈值的考场标记为"建议不开"
```

**作弊/扣分考生前排**：
```
如果 cheater_near_front 启用：有作弊记录的学生不在该考场的前 2 排 → 违规
如果 penalized_near_front 启用：扣分 > 0 的学生不在该考场的前 2 排 → 违规
判断来源：Student.cheating_record（非空=有作弊）, Student.penalty（>0=有扣分）
```

### 4.4 软约束与硬约束区分

- **硬约束**：必须满足，违规则方案无效
- **软约束**：尽量满足，作为优化目标的一部分
- 以上所有布尔型约束默认是硬约束
- `balance_rooms`、`teacher_balance` 是软约束——在算法目标函数中作为惩罚项

---

## 五、算法实现

### 5.1 抽象基类（`src/algorithm_base.py`）

```python
class BaseSolver(ABC):
    def __init__(self, config: ConstraintConfig):
        self.config = config

    @abstractmethod
    def solve(
        self,
        session: ExamSession,
        classrooms: list[Classroom],
        students: dict[str, Student],
    ) -> ExamResult:
        """返回符合约束的排座方案"""
        pass
```

### 5.2 模拟退火（`src/sa_solver.py`）—— **首要实现**

#### 5.2.1 核心流程

```
1. 初始化：
   - 将所有参加该场考试的学生随机分配到各考场的可用座位
   - 确保每个考场人数 ≤ 可用座位数
   - 多余学生放入"溢出列表"（后续优化中尝试消化）

2. 目标函数 energy(result):
   return 硬约束违规数量 × 1000 + 空座位总数 × 1 + 软约束惩罚

3. 邻域扰动（随机选一种）：
   a. 交换两个已占座位的 student_id（90% 概率）
   b. 将一个学生移到空座位（8% 概率）
   c. 将两个不同考场的已占座位互换学生（2% 概率）

4. 退火计划：
   T_start = 100.0
   T_end = 0.01
   cooling_rate = 0.9995  （每 100 次迭代后 T *= cooling_rate）
   max_iterations = 10 * N（N = 学生总数，可配置）

5. 接受准则（Metropolis）：
   delta = energy(new) - energy(current)
   if delta < 0: 接受
   else: 以 exp(-delta / T) 概率接受
```

#### 5.2.2 可配置参数（Web 页面上可调）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `T_start` | 100.0 | 初始温度 |
| `T_end` | 0.01 | 终止温度 |
| `cooling_rate` | 0.9995 | 冷却速率 |
| `iterations_per_temp` | 100 | 每个温度下的迭代次数 |
| `restart_count` | 3 | 退火重启次数（取最优） |

### 5.3 蚁群算法（`src/aco_solver.py`）—— 可选

#### 5.3.1 核心思路

```
信息素矩阵：pheromone(student_idx, seat_idx) = 该学生放在该座位上的"好感度"

每轮迭代：
1. N_ants 只蚂蚁各自独立构建排座方案
   - 每只蚂蚁按信息素 + 启发式因子 的概率依次为学生选择座位
2. 对每只蚂蚁的方案计算目标函数
3. 信息素更新：
   tau(s, seat) = (1-rho) × tau(s, seat) + 1/energy(best_ant)  [只对最优蚂蚁]
4. 信息素蒸发：所有位置上 rho = 0.1 的蒸发率
```

#### 5.3.2 可配置参数

| 参数 | 默认值 |
|------|--------|
| `n_ants` | 20 |
| `n_iterations` | 200 |
| `evaporation_rate` | 0.1 |
| `alpha` (信息素权重) | 1.0 |
| `beta` (启发式权重) | 2.0 |

### 5.4 算法实现通用规则

- **必须对每次迭代记录 energy 值**，供评估报告绘制收敛曲线
- **必须能在任意迭代后中断并返回当前最优**——Web 请求不能无限阻塞
- **必须处理无解情况**：所有重启后仍然无法满足硬约束时，返回"不可满足"并列出无法消解的违规

---

## 六、Web 页面规范

### 6.1 统一 UI 风格

- **配色**：浅灰背景 `#f5f5f5`，主色调蓝 `#2c7be5`，成功绿 `#00d97e`，警告橙 `#f6c343`，错误红 `#e63757`
- **字体**：系统默认栈 `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- **组件库**：不使用任何 CSS 框架；用纯 CSS 手写，保持轻量
- **座位网格**：用 `<table>` 渲染，每个 `<td>` 根据班级背景色填充

### 6.2 页面流程图

```
/upload          → 上传 5 CSV（students/classes/classrooms/subjects/teachers）+ 网格编辑器微调考场
    ↓
/config          → 勾选约束 + 选择算法 + 调参数 + 配置考试场次（从科目中选择）
    ↓
/run             → POST 触发计算 → 返回首个结果视图
    ↓
/result/{type}   → 4 个标签页切换维度
    ├── classroom  → 每个考场的座位网格图
    ├── student    → 搜索学号/姓名 → 显示该生各场考试的座位（卡片式）
    ├── teacher    → 监考分配表（如果配置了监考数据）
    └── class      → 班级分布热力图/柱状图
    ↓
/report          → 手动点击生成评估报告（收敛曲线 + 统计指标）
    ↓
/export/{format} → JSON 或 CSV 下载
```

### 6.3 考场网格编辑器（上传页面的核心组件）

```
用户操作流程：
1. 输入教室编号（如 "C201"）
2. 输入行数 rows、列数 cols
3. 页面渲染 rows × cols 的表格
4. 点击格子切换状态：
   - 默认：绿色边框（可用）
   - 点击一次：灰色底色 ×（标记为 blocked）
   - 再点击一次：恢复绿色
5. 点击"添加考场" → 保存该考场配置到列表
6. 可添加多个考场
7. 支持"从 CSV 导入考场列表"（批量导入）
```

CSV 导入考场格式示例（与 `data/classrooms.csv` 列头一致）：
```csv
building,capacity,room_id,floor,available,seat_layout,notes
A,48,201,2,是,8×6,
B,30,105,1,是,6×5!(3,3),
C,64,301,3,是,8×8,阶梯教室
D,0,B1,B1,否,,地下考场暂不可用
```
`seat_layout` 格式见 2.2 节：`{rows}×{cols}` 或 `{rows}×{cols}!{blocked}`。`available` = "否" 的考场不参与排座。

### 6.4 4 维度可视化要求

#### 考场维度（`result_classroom.html`）
- 每个考场渲染为座位网格表
- 空座：浅灰底色，显示 "—"
- 已占座：班级对应颜色底色，显示学号后 3 位
- 点击某个座位：弹出 tooltip 显示完整信息（学号、姓名、班级、作弊记录、扣分）
- 阻塞格：深灰底色，无文字
- 图例：右侧列出班级 → 颜色映射表

#### 考生维度（`result_student.html`）
- 搜索框（输入学号或姓名，实时过滤）
- 匹配到的学生以卡片展示（含作弊标记 ⚠ 和扣分标记）：
  ```
  ┌──────────────────────────────────┐
  │ 张三  S1001  高三1班  ⚠作弊 扣3分 │
  │ 数学  01-20 08:00  A201-3-2      │
  │ 语文  01-20 14:00  B105-5-1      │
  │ 英语  01-21 08:00  A201-1-6      │
  └──────────────────────────────────┘
  ```

#### 老师维度（`result_teacher.html`）
- 表格式视图：每位监考老师负责的考场 × 考试场次矩阵
- 如果 `teacher_avoid_own_class` 启用，标红违规项

#### 班级维度（`result_class.html`）
- 柱状图（Chart.js）：各班在各考场的分布人数
- 热力图（CSS Grid）：每个考场内该班学生的座位散布
- 下拉框选择班级 → 高亮该班所有考场中的所有座位

### 6.5 导出功能

| 格式 | 触发方式 | 内容 |
|------|----------|------|
| JSON | 按钮"导出完整结果" | 完整的 `ExamResult` 序列化 |
| CSV | 按钮"导出名单" | 扁平化：`session,room,building,row,col,student_id,name,class_id,cheating_record,penalty` |

CSV 导出示例：
```csv
session,subject,room,building,row,col,student_id,name,class_id,cheating_record,penalty
语文-0120上午,语文,A201,A,1,1,S1001,张三,高三1班,,0
语文-0120上午,语文,A201,A,1,2,,, ,,
语文-0120上午,语文,A201,A,1,3,S1003,王五,高三2班,,0
```

---

## 七、评估报告（`src/evaluator.py` + `/report`）

### 7.1 仅在用户手动点击"生成评估报告"时触发

点击后后端执行评估，返回 `/report` 页面。

### 7.2 报告内容

| 指标 | 展示方式 |
|------|----------|
| 收敛曲线 | Chart.js 折线图：x 轴迭代次数，y 轴 energy |
| 最终约束满足率 | 百分比环形图：绿=满足，红=违规 |
| 考场利用率 | 每个考场的柱状图（已用/可用） |
| 班级隔离度 | 同班相邻对数 / 总相邻座位对 |
| 运算耗时 | 纯文本 |

### 7.3 Evaluator 类签名

```python
class Evaluator:
    def evaluate(self, result: ExamResult, energy_history: list[float]) -> EvaluationReport:
        pass

@dataclass
class EvaluationReport:
    energy_curve: list[float]
    constraint_pass_rate: float      # 0~1
    room_utilization: dict[str, float]  # room_id → 利用率
    class_isolation_score: float
    time_elapsed: float
```

---

## 八、输入数据格式

> **以下所有格式与 `data/` 目录下的 CSV 列头严格一致。**
> **编码**：所有 CSV 文件统一使用 **UTF-8**（带 BOM 自动检测）。

### 8.1 Students CSV（`students.csv`）—— 必须上传

| Column | Type | Description |
|--------|------|-------------|
| `student_id` | str | Unique identifier |
| `name` | str | Student name |
| `gender` | str | 男/女 (M/F) |
| `class_id` | str | e.g. "高三1班", one student belongs to exactly one class |
| `dormitory` | str | Dormitory number |
| `elective_subjects` | str | Semicolon-delimited, e.g. "日语;美术" |
| `cheating_record` | str | Empty = no record; any content = has record |
| `penalty` | int | 0 or positive integer |
| `id_number` | str | 18-digit national ID |
| `contact` | str | Phone number |
| `notes` | str | Free text |

示例：
```csv
student_id,name,gender,class_id,dormitory,elective_subjects,cheating_record,penalty,id_number,contact,notes
S1001,张三,男,高三1班,A101,日语,,0,310101200501010001,13800001111,
S1002,李四,女,高三1班,A102,美术,夹带纸条,3,310101200502020002,13800002222,
S1003,王五,男,高三2班,B201,,,0,310101200503030003,13800003333,
```

### 8.2 Classes CSV（`classes.csv`）—— 必须上传

| Column | Type | Description |
|--------|------|-------------|
| `class_id` | str | Class name, linked to `students.csv` `class_id` |
| `student_count` | int | Number of students |
| `advisor` | str | Advisor name |
| `major` | str | Major name |
| `grade` | str | e.g. "高三" |
| `classroom_id` | str | Default classroom |
| `notes` | str | Free text |

示例：
```csv
class_id,student_count,advisor,major,grade,classroom_id,notes
高三1班,45,赵老师,理科,高三,A201,
高三2班,42,钱老师,文科,高三,A202,
```

### 8.3 Classrooms CSV（`classrooms.csv`）—— 必须上传

| Column | Type | Description |
|--------|------|-------------|
| `building` | str | e.g. "A", "B", "C" |
| `capacity` | int | Maximum capacity |
| `room_id` | str | e.g. "201", combined with building → "A201" |
| `floor` | int | Floor number |
| `available` | str | "是"/"否" → True/False |
| `seat_layout` | str | `{rows}×{cols}` or `{rows}×{cols}!{blocked}` (see §2.2) |
| `notes` | str | Free text |

示例：
```csv
building,capacity,room_id,floor,available,seat_layout,notes
A,48,201,2,是,8×6,
B,30,105,1,是,6×5!(3,3),
C,64,301,3,是,8×8,阶梯教室
D,0,B1,B1,否,,地下考场暂不可用
```

### 8.4 Subjects CSV（`subjects.csv`）—— 必须上传

| Column | Type | Description |
|--------|------|-------------|
| `name` | str | Subject name, e.g. "数学" |
| `code` | str | Subject code, e.g. "MATH" |
| `type` | str | e.g. "必修", "选修" |
| `class_id` | str | Target class (linked to `classes.csv` `class_id`) |
| `teacher_name` | str | Teacher name (linked to `teachers.csv` `name`) |
| `duration_minutes` | int | Exam duration in minutes |
| `room_capacity` | int | Required classroom capacity |
| `notes` | str | Free text |

示例：
```csv
name,code,type,class_id,teacher_name,duration_minutes,room_capacity,notes
数学,MATH,必修,高三1班,张老师,120,48,
语文,CHIN,必修,高三1班,李老师,150,48,
英语,ENGL,必修,高三1班,王老师,120,48,
日语,JAPN,选修,高三1班,赵老师,90,30,
```

### 8.5 Teachers CSV（`teachers.csv`）—— 可选上传（仅监考分配需要）

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | str | Unique identifier |
| `name` | str | Teacher name |
| `gender` | str | 男/女 |
| `subject` | str | Subject taught (linked to `subjects.csv` `name`) |
| `phone` | str | Contact number |
| `invigilation_qualified` | str | "是"/"否" → True/False |
| `title` | str | e.g. "高级教师" |
| `notes` | str | Free text |

示例：
```csv
employee_id,name,gender,subject,phone,invigilation_qualified,title,notes
T001,张老师,男,数学,13900001111,是,高级教师,
T002,李老师,女,语文,13900002222,是,一级教师,
T003,王老师,男,英语,13900003333,否,二级教师,无监考资格
```

### 8.6 考试场次配置

在 `/config` 页面手动添加（不从 CSV 导入，从已上传的 subjects 中选择）：
```
场次ID:   MATH_20250120_AM
科目:     数学（从已上传的 subjects.csv 中选择）
日期时间:  2025-01-20 08:00-10:00
参考班级:  高三1班, 高三2班, 高三3班   （从已上传的 students 中筛选）
```

支持添加多个场次（"+ 添加场次"按钮）。

---

## 九、禁止事项（Agent 必须遵守）

1. ❌ **禁止用贪心算法替代启发式算法**——贪心只能用于生成初始解或对比基线
2. ❌ **禁止硬编码测试数据**——所有数据必须从 CSV 读取或 Web 上传
3. ❌ **禁止跳过约束校验**——输出结果前必须逐条验证并生成违规报告
4. ❌ **禁止假设输入数据无异常**——必须处理空班级、人数超容、考场不足、无解等边界情况
5. ❌ **禁止在前端执行算法**——核心算法必须在 Python 后端同步执行
6. ❌ **禁止写死算法参数**——种群规模、迭代次数、退火速率等必须在 Web 页面可配置
7. ❌ **禁止引入 React/Vue 等前端框架**——前端仅用原生 JS + Chart.js
8. ❌ **禁止跳过测试**——每个核心模块必须有对应的单元测试
9. ❌ **禁止创造新文件不更新 tests/ 和 docs/**——新增模块必须同步更新测试和文档
10. ❌ **禁止修改学生-班级的一对一关系**——一个学生只属于一个班级
11. ❌ **禁止硬编码 CSV 列头映射**——所有列头映射必须从实际 CSV 第一行读取，以 `data/` 目录下的列头为唯一真相源
12. ❌ **禁止忽略 5 张 CSV 的关联关系**——`classes ↔ students`（class_id），`subjects ↔ classes`（class_id），`subjects ↔ teachers`（teacher_name），必须全部正确关联
13. ❌ **禁止假设座位布局只有纯网格**——必须解析 `seat_layout` 列中的 `!blocked` 部分

---

## 十、后端 API 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 重定向到 `/upload` |
| `/upload` | GET | 上传页面 |
| `/upload` | POST | 接收 5 个 CSV（students/classes/classrooms/subjects/teachers），存入 session；teachers 可选 |
| `/config` | GET | 约束勾选 + 算法选择 + 参数配置 + 场次配置 |
| `/config` | POST | 保存配置到 session |
| `/run` | POST | 触发算法运行，重定向到 `/result/classroom` |
| `/result/<view>` | GET | 渲染 4 个维度视图之一 |
| `/report` | POST | 生成评估报告 |
| `/export/<format>` | GET | 下载 JSON 或 CSV |

---

## 十一、错误处理与边界情况（必须处理）

| 场景 | 处理方式 |
|------|----------|
| 学生人数 > 所有考场总可用座位数 | 返回错误："考场容量不足，缺少 X 个座位"，不执行算法 |
| 某班级人数 > 任一考场可用座位数 | 警告："班级 X 人数超过单考场容量，无法完全隔离" |
| 所有学生都集中在少数班级 | 可能无解，SA 返回最佳近似 + 违规列表 |
| CSV 编码非 UTF-8 | 检测 BOM，自动转换；失败则提示用户 |
| 座位布局解析失败 | 校验并拒绝："考场 A201 的座位布局 '8x6' 格式错误（应为 8×6）" |
| blocked 坐标越界 | 校验并拒绝："考场 A201 的阻塞坐标 (9,3) 超出范围 [1-8, 1-6]" |
| 某场考试无人参加 | 跳过该场次，在结果中标注"无考生" |
| 算法超时 | 设置 120 秒超时，返回当前最优解 + 警告"算法未收敛" |
| classes.csv 的 class_id 与 students.csv 的 class_id 不匹配 | 警告列出孤立班级和未匹配学生，允许继续但标红 |
| subjects.csv 的 teacher_name 不在 teachers.csv 中 | 警告，监考分配时跳过该科目 |
| classrooms.csv 的 capacity < seat_layout 可用座位数 | 警告："考场 X 声明的 capacity Y 小于 seat_layout 可用座位数 Z" |

---

## 十二、测试要求（`tests/`）

### 12.1 每个测试文件的最低覆盖

| 文件 | 必须覆盖 |
|------|----------|
| `test_models.py` | 6 个数据类（Student/ClassGroup/Classroom/Subject/Teacher/ExamSession）的构造与序列化；seat_layout 解析为 rows/cols/blocked；空 blocked 和不规则布局 |
| `test_seat_graph.py` | 规则矩形邻接生成、含阻塞格的邻接、四邻/八邻切换、边缘座位只有 3 个邻居 |
| `test_constraint_engine.py` | 每种约束至少 1 正例 1 反例、多约束组合、软约束不计入硬违规、cheater_near_front + penalized_near_front 独立测试 |
| `test_sa_solver.py` | 简单场景（2 考场、10 学生）能在 1000 次迭代内找到合法解、energy 单调不增（允许偶尔上升）、重启取最优 |
| `test_aco_solver.py` | 同上简单场景验证、信息素矩阵维度正确 |
| `test_integration.py` | 上传 5 CSV（students/classes/classrooms/subjects/teachers）→ 配置约束 → 运行 → 导出 JSON → 导出 CSV → 验证 CSV 行数 |

### 12.2 测试数据

`data/` 目录下必须包含（与项目 data/ 实际列头一致）：
- `students.csv`：至少 50 个学生、3 个班级，含 cheating_record 和 penalty 样本
- `classes.csv`：至少 3 个班级
- `classrooms.csv`：至少 3 个考场，其中至少 1 个含阻塞格（`seat_layout` 含 `!`）
- `subjects.csv`：至少 4 个科目
- `teachers.csv`：至少 3 位老师，至少 1 位 invigilation_qualified = "否"

---

## 十三、文档要求（`docs/`）

| 文档 | 必须包含 |
|------|----------|
| `ALGORITHM.md` | SA 和 ACO 的算法描述、参数含义、邻域扰动策略、收敛性讨论 |
| `API.md` | 所有路由的请求/响应格式、所有数据类的字段说明 |
| `USER_GUIDE.md` | 从上传到导出完整操作流程、截图建议（可用文字描述替代）、常见问题 |

---

## 十四、班级颜色映射

为每个班级自动分配可区分颜色（最多 12 种，超出循环）：

```
高三1班 → #4dc9f6
高三2班 → #f67019
高三3班 → #f53794
高三4班 → #537bc4
高三5班 → #acc236
高三6班 → #166a8f
高三7班 → #00a950
高三8班 → #58595b
高三9班 → #8549ba
高三10班 → #e6194b
高三11班 → #3cb44b
高三12班 → #ffe119
（12 种以上循环）
```
