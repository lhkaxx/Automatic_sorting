# API 文档 — 考场自动排座系统

## 路由概览

| 方法 | 路由 | 功能 |
|------|------|------|
| GET/POST | `/upload` | 上传 CSV 数据文件 |
| GET/POST | `/config` | 配置约束、选择算法、创建考试场次 |
| POST | `/run` | 触发排座计算 |
| GET | `/result/classroom` | 考场视图 — 座位网格 |
| GET | `/result/student` | 考生视图 — 搜索查询 |
| GET | `/result/teacher` | 教师视图 — 监考分配表 |
| GET | `/result/class` | 班级视图 — 分布图 |
| GET | `/report` | 评估报告（含 `?generate=1` 触发生成） |
| GET | `/export/json` | 下载 JSON 结果 |
| GET | `/export/csv` | 下载 CSV 名单 |

## 数据模型

### Student

| 字段 | 类型 | CSV列 | 说明 |
|------|------|-------|------|
| student_id | str | student_id | 学号，唯一标识 |
| name | str | name | 姓名 |
| gender | str | gender | 男/女 |
| class_id | str | class_id | 班级名 |
| dormitory | str | dormitory | 寝室号 |
| elective_subjects | list[str] | elective_subjects | 分号分隔 |
| cheating_record | str | cheating_record | 非空=有记录 |
| penalty | int | penalty | 0=无扣分 |
| id_number | str | id_number | 身份证号 |
| contact | str | contact | 手机号 |
| notes | str | notes | 备注 |

### Classroom

| 字段 | 类型 | CSV列 | 说明 |
|------|------|-------|------|
| building | str | building | 楼号 (A/B/C) |
| capacity | int | capacity | 最大容纳人数 |
| room_id | str | room_id | 教室编号 |
| floor | int | floor | 楼层 |
| available | bool | available | 是否可用 |
| seat_layout | str | seat_layout | "8×6" 或 "8×6!(4,1);(8,6)" |
| rows | int | (派生) | 行数 |
| cols | int | (派生) | 列数 |
| blocked_seats | list[(int,int)] | (派生) | 阻塞座坐标 |

### ExamSession

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | str | "MATH_20250120_AM" |
| subject | Subject | 科目对象 |
| datetime | str | "2025-01-20 08:00-10:00" |
| student_ids | list[str] | 考生学号列表 |

### ExamResult

| 字段 | 类型 | 说明 |
|------|------|------|
| session | ExamSession | 考试场次 |
| classrooms | list[ClassroomResult] | 各考场结果 |
| metadata | dict | 算法/参数/耗时信息 |

## seat_layout 格式

### 纯网格
```
8×6
```
→ 8 行 6 列，48 个座位，无阻塞

### 含阻塞格
```
6×5!(3,3)
```
→ 6 行 5 列，(3,3) 不可用

```
8×6!(4,1);(4,2);(8,6)
```
→ 多个阻塞格用 `;` 分隔

## JSON 导出格式

```json
{
  "session": { "session_id": "...", "subject": {...}, "datetime": "..." },
  "classrooms": [
    {
      "room_id": "A201",
      "rows": 8,
      "cols": 6,
      "blocked": [],
      "seats": [
        { "room_id": "A201", "row": 1, "col": 1, "student_id": "S1001", "student_name": "张三", "class_id": "高三1班" }
      ]
    }
  ],
  "metadata": { "algorithm": "SA", "iterations": 5000, "time_elapsed": 12.3 }
}
```

## CSV 导出格式

```csv
session,subject,room,building,row,col,student_id,name,class_id,cheating_record,penalty
语文-0120上午,语文,A201,A,1,1,S1001,张三,高三1班,,0
```
