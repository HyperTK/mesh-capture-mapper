"""メッシュ番号 ↔ 格子インデックス(col,row) ↔ 緯度経度 の変換。

格子規則の正体（KMZ画像の実測で確定）:
  メッシュ番号は `<英字>-<3桁数字>` 形式（例: C-374）の独自再帰分割コード。
    - 一の位 d0: 2x2セル内の位置  {3:左上, 4:右上, 1:左下, 2:右下}
    - 十の位 d1: 東西方向の2セル束（西→東で増加）
    - 百の位 d2: 南北方向の2セル束（北→南で変化）
    - 英字     : 東西の大ブロック
  → 「mesh → (col, row) 対応表」を真実の源とする（仕様の「対応表方式」）。

座標化（重要・ピクセルアンカー方式）:
  KMZ画像にメッシュ番号が印字されている。OCR/実測で複数メッシュの
  印字ピクセル中心 (x, y) を取り、最小二乗で col/row とピクセルの線形関係
    x = col_w_px * col + x0_px
    y = row_h_px * row + y0_px
  を求めてある（src/build_grid_from_image.py で算出。GridCalibration）。
  四隅 bbox（rotation=0、北が上）と合成して col/row -> 緯度経度を厳密化する:
    lon = west  + (east  - west ) * (x / IMG_W)
    lat = north - (north - south) * (y / IMG_H)
  これにより「総セル数で bbox を等分」する近似を避け、画像と直接整合する。

  ※以前は (east-west)/n_cols で等分していたが、画像端がセルの途中で切れて
    いるため n_cols/n_rows が非整数となり、格子が画像とズレていた。
    ピクセルアンカー方式はこの問題を起こさない。

  較正の有効範囲（重要）:
    アンカーは C系（col 0..6）中心で取得しており、col_w_px=152 を col>=7 まで
    外挿すると セル中心 px が画像右端(1116px)を超える。画像オーバーレイは
    その東側を含まないため、col>=7 のセルは bbox の外へ外挿され、格子全体が
    東に伸びて縦長に歪む。対応表 (mesh_grid.csv) は col<=6 のみを採用する。
    D系の東端（col>=7）を座標化するには、その領域を含む別の画像と LatLonBox が必要。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


# KMZ doc.kml の LatLonBox（基準座標）。
@dataclass(frozen=True)
class BBox:
    north: float
    south: float
    east: float
    west: float


SHIZUKUISHI_BBOX = BBox(
    north=39.94402642,
    south=39.28291197,
    east=141.06817802,
    west=140.60895931,
)

# KMZ overlay 画像サイズ（px）。
IMG_W = 1116
IMG_H = 2061


@dataclass(frozen=True)
class GridCalibration:
    """col/row -> 画像ピクセル の線形較正（OCRアンカーの最小二乗フィット由来）。

    x = col_w_px * col + x0_px
    y = row_h_px * row + y0_px
    既定値は src/build_grid_from_image.py のアンカー実測フィット結果。
    """

    # 較正手順:
    #  傾き(col_w_px/row_h_px): 高解像度PDF(2866x4055)で col/row を確定し、
    #    KMZ画像(1116x2061)の共通メッシュ12点でフィット（残差 x<2.3px, y<1.1px）。
    #  切片(x0_px/y0_px): 上記フィットはメッシュ「印字」位置基準で、印字はセル中心
    #    から系統的にずれている（印字はセル左上寄り）。そこで KMZ画像の格子線を実測し、
    #    切片をセル「中心」基準に補正した（印字→中心 dx=+32, dy=+52）。
    #    検証: セル境界予測が実測格子線(y=63,195,326 / x=185,336)と±1〜3pxで一致。
    col_w_px: float = 151.995
    x0_px: float = 105.44
    row_h_px: float = 131.079
    y0_px: float = 128.84
    img_w: int = IMG_W
    img_h: int = IMG_H

    def cell_px_bounds(self, col: int, row: int) -> tuple[float, float, float, float]:
        """セルのピクセル境界 (x_left, x_right, y_top, y_bottom) を返す。

        セル中心が x = col_w_px*col + x0_px なので、境界は ±半セル。
        """
        cx = self.col_w_px * col + self.x0_px
        cy = self.row_h_px * row + self.y0_px
        return (cx - self.col_w_px / 2, cx + self.col_w_px / 2,
                cy - self.row_h_px / 2, cy + self.row_h_px / 2)


DEFAULT_CALIBRATION = GridCalibration()


# 象限 -> セル内の (東西位置, 南北位置)。0..1 の正規化座標。
# 西=0/東=1、北=0/南=1 の格子内で、各 1/4 セルの中心を採る。
QUADRANT_CENTER = {
    "左上": (0.25, 0.25),  # 西側1/2・北側1/2 の中心
    "右上": (0.75, 0.25),  # 東側1/2・北側1/2 の中心
    "左下": (0.25, 0.75),  # 西側1/2・南側1/2 の中心
    "右下": (0.75, 0.75),  # 東側1/2・南側1/2 の中心
}


def normalize_mesh(mesh: str) -> str:
    """メッシュ番号の表記ゆれを吸収する（全角ハイフン・空白・小文字など）。"""
    s = mesh.strip().upper()
    s = s.replace("−", "-").replace("－", "-").replace("ー", "-")
    s = s.replace("　", "").replace(" ", "")
    return s


def _px_to_lonlat(x: float, y: float, bbox: BBox,
                  img_w: int, img_h: int) -> tuple[float, float]:
    """画像ピクセル (x,y) を緯度経度に（rotation=0, 北が上の線形変換）。"""
    lon = bbox.west + (bbox.east - bbox.west) * (x / img_w)
    lat = bbox.north - (bbox.north - bbox.south) * (y / img_h)
    return lon, lat


@dataclass(frozen=True)
class MeshGrid:
    """mesh -> (col, row) 対応表とピクセル較正・四隅から座標を計算する。"""

    mapping: dict[str, tuple[int, int]]
    bbox: BBox
    calib: GridCalibration

    @classmethod
    def from_csv(cls, path: str | Path, bbox: BBox = SHIZUKUISHI_BBOX,
                 calib: GridCalibration = DEFAULT_CALIBRATION) -> "MeshGrid":
        """対応表 CSV（列: mesh,col,row）を読み込む。"""
        mapping: dict[str, tuple[int, int]] = {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mesh = normalize_mesh(row["mesh"])
                mapping[mesh] = (int(row["col"]), int(row["row"]))
        if not mapping:
            raise ValueError(f"対応表が空です: {path}")
        return cls(mapping=mapping, bbox=bbox, calib=calib)

    @property
    def n_cols(self) -> int:
        return max(c for c, _ in self.mapping.values()) + 1

    @property
    def n_rows(self) -> int:
        return max(r for _, r in self.mapping.values()) + 1

    def cell_bounds(self, col: int, row: int) -> tuple[float, float, float, float]:
        """セルの境界 (west_lon, east_lon, north_lat, south_lat) を返す。

        ピクセル較正でセルのピクセル枠を求め、四隅 bbox で緯度経度に変換する。
        row は北(0)→南 に増加。
        """
        xl, xr, yt, yb = self.calib.cell_px_bounds(col, row)
        west_lon, north_lat = _px_to_lonlat(xl, yt, self.bbox,
                                            self.calib.img_w, self.calib.img_h)
        east_lon, south_lat = _px_to_lonlat(xr, yb, self.bbox,
                                            self.calib.img_w, self.calib.img_h)
        return west_lon, east_lon, north_lat, south_lat

    def point(self, mesh: str, quadrant: str) -> tuple[float, float]:
        """メッシュ番号＋象限から代表点 (lon, lat) を返す。

        位置精度はセルの 1/4（おおよそのエリア代表点）。
        """
        key = normalize_mesh(mesh)
        if key not in self.mapping:
            raise KeyError(f"対応表に未登録のメッシュ番号: {mesh!r}（正規化: {key!r}）")
        quadrant = quadrant.strip()
        if quadrant not in QUADRANT_CENTER:
            raise KeyError(f"未知の象限: {quadrant!r}（許容: {list(QUADRANT_CENTER)}）")

        col, row = self.mapping[key]
        west_lon, east_lon, north_lat, south_lat = self.cell_bounds(col, row)
        fx, fy = QUADRANT_CENTER[quadrant]  # fx:西0→東1, fy:北0→南1
        lon = west_lon + (east_lon - west_lon) * fx
        lat = north_lat - (north_lat - south_lat) * fy
        return lon, lat
