---
name: writing-plans
description: 将设计规范拆分为 2-5 分钟的单元任务，精确到文件路径和验收标准，按依赖拓扑排序。
---

# Writing Plans — 实施计划拆分

## 何时使用

当你有了一份经过确认的设计文档/规范后，在写任何代码之前，先调用此技能。

## 核心原则

- **每个任务 2-5 分钟可完成** — 这是一个"单元任务"的粒度
- **每个任务精确到文件路径** — 不写"完善代码"，写"在 `src/models.py` 中添加 Student dataclass"
- **每个任务包含验收标准** — 不写"实现约束引擎"，写"运行 `pytest tests/test_constraint_engine.py -v` 全部通过"
- **YAGNI** — 你不需要的东西就别做
- **DRY** — 发现重复就合并

## 拆分流程

### 1. 阅读设计文档

先完整阅读项目的设计规范/SPEC，理解：
- 数据模型是什么
- 模块依赖关系（谁依赖谁）
- 哪些可以并行，哪些必须串行

### 2. 识别模块依赖图

```
输出模块依赖关系，标注串行/并行：

src/models.py          ← 所有模块都依赖它，必须最先
    ↓
src/io_handler.py      ← 依赖 models，可和 seat_graph 并行
src/seat_graph.py      ← 依赖 models，可和 io_handler 并行
    ↓
src/constraint_engine.py ← 依赖 models + seat_graph
    ↓
src/algorithm_base.py  ← 依赖 models
src/sa_solver.py       ← 依赖 algorithm_base + constraint_engine
src/aco_solver.py      ← 依赖 algorithm_base + constraint_engine
    ↓
src/evaluator.py       ← 依赖 models
    ↓
app.py                 ← 依赖所有 src 模块
templates/*            ← 可和 app.py 并行
static/*               ← 可并行
tests/*                ← 每个源文件完成后立即写测试
```

### 3. 拆分任务

对每个叶子模块，拆出 2-5 分钟的任务：

```
任务模板：
├── 任务 ID: step-N
├── 目标文件: src/xxx.py
├── 内容: 具体要实现什么
├── 验收: pytest tests/test_xxx.py -v 通过 / curl 验证 / 肉眼检查
├── 依赖: step-X, step-Y（必须先完成的任务）
└── 预计耗时: ~3 分钟
```

### 4. 排序输出

按依赖拓扑排序，将任务列表输出给用户确认。格式：

```markdown
## 实施计划

### 第一阶段：基础设施（可并行）
| 任务 | 文件 | 内容 | 验收 |
|------|------|------|------|
| step-1 | src/models.py | 6 个 dataclass | pytest tests/test_models.py |
| step-2 | data/sample_students.csv | 50 学生样本 | pd.read_csv 无报错 |
| step-3 | data/sample_classrooms.csv | 3 考场样本 | pd.read_csv 无报错 |

### 第二阶段：核心逻辑（串行）
| step-4 | src/seat_graph.py | 邻接图构建 | pytest tests/test_seat_graph.py |
| step-5 | src/constraint_engine.py | 12 项约束校验 | pytest tests/test_constraint_engine.py |
| ...

### 第三阶段：算法
...

### 第四阶段：Web 层
...

### 第五阶段：集成
...
```

## 规则

- 禁止一个任务跨多个文件（太容易出错）
- 禁止一个任务超过 5 分钟（拆得不够细）
- 测试文件必须紧挨着对应源文件安排（不要最后统一写测试）
- 标注依赖关系，确保执行顺序正确
