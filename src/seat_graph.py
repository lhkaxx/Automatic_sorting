"""
邻接图构建 — 将网格 + 阻塞格转换为邻接图，供约束引擎高效查询。

两种邻接模式：
  - 四邻：曼哈顿距离 = 1  (上下左右)
  - 八邻：切比雪夫距离 = 1 (含对角线)
"""

from .models import Classroom


class RoomGraph:
    """单个考场的邻接图"""

    def __init__(self, room_id: str, rows: int, cols: int,
                 blocked_seats: list[tuple[int, int]],
                 adjacency_mode: str = "four"):
        """
        Args:
            room_id: 考场标识
            rows: 行数
            cols: 列数
            blocked_seats: 阻塞座位列表 (row, col) 1-indexed
            adjacency_mode: "four" (四邻) 或 "eight" (八邻)
        """
        self.room_id = room_id
        self.rows = rows
        self.cols = cols
        self.adjacency_mode = adjacency_mode

        # 可用座位
        blocked_set = set(blocked_seats)
        self.available_seats: list[tuple[int, int]] = [
            (r, c)
            for r in range(1, rows + 1)
            for c in range(1, cols + 1)
            if (r, c) not in blocked_set
        ]

        # 邻接表
        self.adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self._build_adjacency()

        # 同排/同列的座位索引
        self.same_row: dict[int, list[tuple[int, int]]] = {}
        self.same_col: dict[int, list[tuple[int, int]]] = {}
        self._build_row_col_index()

    def _build_adjacency(self):
        """构建邻接表"""
        available_set = set(self.available_seats)

        if self.adjacency_mode == "four":
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        else:  # eight
            directions = [
                (-1, -1), (-1, 0), (-1, 1),
                (0, -1),           (0, 1),
                (1, -1),  (1, 0),  (1, 1),
            ]

        for r, c in self.available_seats:
            neighbors = []
            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                if (nr, nc) in available_set:
                    neighbors.append((nr, nc))
            self.adjacency[(r, c)] = neighbors

    def _build_row_col_index(self):
        """构建同行/同列索引"""
        for r in range(1, self.rows + 1):
            self.same_row[r] = [(rr, cc) for (rr, cc) in self.available_seats if rr == r]
        for c in range(1, self.cols + 1):
            self.same_col[c] = [(rr, cc) for (rr, cc) in self.available_seats if cc == c]

    def get_neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        """获取某座位的相邻座位"""
        return self.adjacency.get((row, col), [])

    def get_same_row_seats(self, row: int) -> list[tuple[int, int]]:
        """获取同排所有可用座位"""
        return self.same_row.get(row, [])

    def get_same_col_seats(self, col: int) -> list[tuple[int, int]]:
        """获取同列所有可用座位"""
        return self.same_col.get(col, [])


class SeatGraph:
    """所有考场的邻接图集合"""

    def __init__(self, classrooms: list[Classroom], adjacency_mode: str = "four"):
        """
        Args:
            classrooms: 考场列表
            adjacency_mode: "four" 或 "eight"
        """
        self.rooms: dict[str, RoomGraph] = {}
        for cr in classrooms:
            if cr.available and cr.rows > 0 and cr.cols > 0:
                self.rooms[cr.full_room_id] = RoomGraph(
                    room_id=cr.full_room_id,
                    rows=cr.rows,
                    cols=cr.cols,
                    blocked_seats=cr.blocked_seats,
                    adjacency_mode=adjacency_mode,
                )

    def get_room(self, room_id: str) -> RoomGraph | None:
        return self.rooms.get(room_id)

    def get_adjacent_seats(self, room_id: str, row: int, col: int) -> list[tuple[int, int]]:
        """获取某座位的相邻座位坐标列表"""
        room = self.rooms.get(room_id)
        if room is None:
            return []
        return room.get_neighbors(row, col)
