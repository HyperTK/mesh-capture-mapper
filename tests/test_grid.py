import math
from pathlib import Path

import pytest

from src.grid import MeshGrid, SHIZUKUISHI_BBOX, normalize_mesh

REF = Path(__file__).resolve().parents[1] / "data" / "reference" / "mesh_grid.csv"


@pytest.fixture(scope="module")
def grid():
    return MeshGrid.from_csv(REF)


def test_grid_extent(grid):
    # 対応表が覆う範囲。画像(1116px)に収まる col 0..6 のみを採用する。
    # col>=7（D系の東端）は較正を外挿すると画像右端の外に出るため除外済み。
    assert grid.n_cols == 7
    assert grid.n_rows == 14


def test_all_cells_inside_image(grid):
    # 全セル中心が画像範囲内に収まる（bbox 外への外挿を起こさない）。
    c = grid.calib
    for col, row in grid.mapping.values():
        cx = c.col_w_px * col + c.x0_px
        cy = c.row_h_px * row + c.y0_px
        assert 0 <= cx <= c.img_w, f"col{col} x={cx:.0f} outside 0..{c.img_w}"
        assert 0 <= cy <= c.img_h, f"row{row} y={cy:.0f} outside 0..{c.img_h}"


# KMZ画像(1116x2061)から実測したセル境界（横/縦の格子線ピクセル位置）。
# 較正は「セル中心」基準なので、計算したセル境界がこの実測格子線に一致するか検証する。
# 横線 y: row 0..2 のセル上端。縦線 x: col 1,2 のセル左端。
HLINE_TOP_PX = {0: 63.0, 1: 195.0, 2: 326.0, 3: 456.0, 4: 588.0}
VLINE_LEFT_PX = {1: 185.0, 2: 336.0, 3: 488.0}


def test_cell_top_matches_grid_line(grid):
    # 各 row のセル上端 px が実測横格子線に一致（±4px）。
    c = grid.calib
    for row, y_expect in HLINE_TOP_PX.items():
        y_top = c.row_h_px * row + c.y0_px - c.row_h_px / 2
        assert abs(y_top - y_expect) < 4, f"row{row} top {y_top:.1f} vs {y_expect}"


def test_cell_left_matches_grid_line(grid):
    # 各 col のセル左端 px が実測縦格子線に一致（±5px。縦線は地物ノイズで横線より緩め）。
    c = grid.calib
    for col, x_expect in VLINE_LEFT_PX.items():
        x_left = c.col_w_px * col + c.x0_px - c.col_w_px / 2
        assert abs(x_left - x_expect) < 5, f"col{col} left {x_left:.1f} vs {x_expect}"


def test_point_inside_bbox(grid):
    lon, lat = grid.point("C-374", "右下")
    b = grid.bbox
    assert b.west <= lon <= b.east
    assert b.south <= lat <= b.north


def test_quadrant_relative_positions(grid):
    # 同一メッシュの4象限の相対関係を検証。
    lt = grid.point("C-374", "左上")
    rt = grid.point("C-374", "右上")
    lb = grid.point("C-374", "左下")
    rb = grid.point("C-374", "右下")
    # 左 < 右 (経度), 上 > 下 (緯度)
    assert lt[0] < rt[0]
    assert lb[0] < rb[0]
    assert lt[1] > lb[1]
    assert rt[1] > rb[1]
    # 左右ペアの経度差・上下ペアの緯度差は等しい（セルの1/2）
    assert math.isclose(rt[0] - lt[0], rb[0] - lb[0])
    assert math.isclose(lt[1] - lb[1], rt[1] - rb[1])


def test_quadrant_is_cell_quarter_center(grid):
    # 右下象限の点は、セルの東側1/2・南側1/2の中心にあること。
    col, row = grid.mapping["C-374"]
    w, e, n, s = grid.cell_bounds(col, row)
    lon, lat = grid.point("C-374", "右下")
    assert math.isclose(lon, w + (e - w) * 0.75)
    assert math.isclose(lat, n - (n - s) * 0.75)


def test_north_cell_is_more_north(grid):
    # C-663 (最北行) は C-051 (最南行) より緯度が高い。
    _, lat_north = grid.point("C-663", "左上")
    _, lat_south = grid.point("C-051", "左下")
    assert lat_north > lat_south


def test_east_cell_is_more_east(grid):
    # D系 は C系 より東。
    lon_d, _ = grid.point("D-501", "左上")
    lon_c, _ = grid.point("C-561", "左上")
    assert lon_d > lon_c


def test_normalize_mesh():
    assert normalize_mesh(" c-374 ") == "C-374"
    assert normalize_mesh("Ｃ－３７４".translate(str.maketrans("Ｃ３７４", "C374"))) in ("C-374",)
    assert normalize_mesh("D－303") == "D-303"


def test_unknown_mesh_raises(grid):
    with pytest.raises(KeyError):
        grid.point("Z-999", "左上")


def test_unknown_quadrant_raises(grid):
    with pytest.raises(KeyError):
        grid.point("C-374", "まんなか")
