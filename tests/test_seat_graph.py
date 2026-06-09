"""测试邻接图构建"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Classroom
from src.seat_graph import SeatGraph, RoomGraph


def make_classroom(room_id="201", rows=8, cols=6, blocked=None):
    return Classroom(
        building="A", capacity=rows*cols, room_id=room_id,
        floor=2, available=True, rows=rows, cols=cols,
        blocked_seats=blocked or [],
    )


class TestRoomGraph:
    def test_available_seats(self):
        graph = RoomGraph("A201", 3, 3, [])
        assert len(graph.available_seats) == 9
        assert (1, 1) in graph.available_seats
        assert (3, 3) in graph.available_seats

    def test_available_seats_with_blocked(self):
        graph = RoomGraph("A201", 3, 3, [(1, 1), (2, 2)])
        assert len(graph.available_seats) == 7
        assert (1, 1) not in graph.available_seats
        assert (2, 2) not in graph.available_seats
        assert (3, 3) in graph.available_seats

    def test_four_adjacency_corner(self):
        graph = RoomGraph("A201", 3, 3, [], adjacency_mode="four")
        # 角落 (1,1) 应该只有 2 个邻居：(1,2) 和 (2,1)
        neighbors = graph.get_neighbors(1, 1)
        assert len(neighbors) == 2
        assert (1, 2) in neighbors
        assert (2, 1) in neighbors

    def test_four_adjacency_center(self):
        graph = RoomGraph("A201", 3, 3, [], adjacency_mode="four")
        # 中心 (2,2) 应该有 4 个邻居
        neighbors = graph.get_neighbors(2, 2)
        assert len(neighbors) == 4

    def test_eight_adjacency_center(self):
        graph = RoomGraph("A201", 3, 3, [], adjacency_mode="eight")
        # 中心应该有 8 个邻居
        neighbors = graph.get_neighbors(2, 2)
        assert len(neighbors) == 8

    def test_same_row(self):
        graph = RoomGraph("A201", 3, 3, [])
        row1 = graph.get_same_row_seats(1)
        assert len(row1) == 3
        assert all(r == 1 for r, c in row1)

    def test_same_col(self):
        graph = RoomGraph("A201", 3, 3, [])
        col1 = graph.get_same_col_seats(1)
        assert len(col1) == 3
        assert all(c == 1 for r, c in col1)


class TestSeatGraph:
    def test_build_from_classrooms(self):
        classrooms = [
            make_classroom("201", 3, 3),
            Classroom("B", 4, "101", 1, available=True, rows=2, cols=2),
        ]
        sg = SeatGraph(classrooms)
        assert "A201" in sg.rooms
        assert "B101" in sg.rooms
        assert len(sg.rooms) == 2

    def test_skip_unavailable(self):
        cr = Classroom("A", 48, "201", 2, available=False, rows=8, cols=6)
        sg = SeatGraph([cr])
        assert "A201" not in sg.rooms
