"""KMZ ハンターマップ画像を OCR し、メッシュ番号のピクセル位置から
対応表 (mesh -> col,row) を画像実測で構築する。

背景:
  メッシュ番号は画像の格子セル中央に印字されている。画像の格子は
  約 20列 × 28行（格子線間隔の実測 ~55px から確定）。
  各メッシュ番号のピクセル中心 (x, y) を OCR で取り、
    col = round((x - x0) / cell_w)
    row = round((y - y0) / cell_h)
  で絶対インデックスに落とす。x0,y0 はセル中心の起点（最西/最北セルの中心）。

これにより、規則の起点ズレ（幽霊列）に依存せず、画像と直接整合する
対応表を作る。OCR の誤認識は後段で正規表現フィルタ＋目視で除く。

依存: pytesseract, Pillow, tesseract 本体（jpn+eng）。
使い方:
  python -m src.build_grid_from_image \
      "有害駆除資料/iwate_shizukuishi_hunter_map.kmz" \
      -o data/reference/mesh_grid.csv
  # KMZ を直接渡すと内部の画像を展開して使う。画像PNG/JPGを直接渡してもよい。
"""

from __future__ import annotations

import argparse
import csv
import re
import tempfile
import zipfile
from pathlib import Path

from .grid import normalize_mesh

MESH_RE = re.compile(r"^[A-Z]-\d{3}$")

# KMZ画像(1116x2061)を高解像度OCRして実測したメッシュ印字ピクセル中心。
# 高解像度PDF(2866x4055)で col/row を高精度確定したうえで選んだ共通12点。
# col/row は規則（src/build_grid.py）で決まる。これらの対応から
# x = col_w_px*col + x0_px, y = row_h_px*row + y0_px を最小二乗フィットし、
# src/grid.GridCalibration の係数を得る（外れ値0, x残差<2.3px, y残差<1.1px）。
OCR_ANCHORS_PX = {
    "C-054": (224.2, 1648.5),
    "C-162": (527.2, 1519.5),
    "C-264": (528.7, 1124.3),
    "C-274": (834.0, 1125.3),
    "C-363": (377.3, 862.7),
    "C-364": (529.7, 863.2),
    "C-461": (375.8, 731.7),
    "C-473": (681.5, 601.5),
    "C-563": (378.8, 338.3),
    "C-663": (379.7, 76.3),
    "C-664": (530.8, 76.8),
    "D-103": (984.8, 1387.7),
}


def _extract_image_from_kmz(kmz_path: Path, workdir: Path) -> Path:
    with zipfile.ZipFile(kmz_path) as z:
        names = z.namelist()
        img_names = [n for n in names
                     if n.lower().endswith((".jpg", ".jpeg", ".png"))
                     or "overlay" in n.lower()]
        if not img_names:
            raise SystemExit(f"KMZ 内に画像が見つかりません: {names}")
        target = img_names[0]
        out = workdir / "overlay.jpg"
        out.write_bytes(z.read(target))
        return out


def _load_image_path(src: Path, workdir: Path) -> Path:
    if src.suffix.lower() == ".kmz":
        return _extract_image_from_kmz(src, workdir)
    return src


def ocr_mesh_positions(image_path: Path) -> list[tuple[str, float, float]]:
    """画像から (mesh, x_center_px, y_center_px) のリストを返す。"""
    try:
        import pytesseract  # type: ignore
        from PIL import Image
    except ImportError as e:
        raise SystemExit(f"pytesseract / Pillow が必要です: {e}")

    img = Image.open(image_path)
    # メッシュ番号は英数字なので eng 主体、ハイフン込みで読む。
    config = "--psm 11 -c tessedit_char_whitelist=ABCDEFGH-0123456789"
    data = pytesseract.image_to_data(
        img, lang="eng", config=config, output_type=pytesseract.Output.DICT)

    # 単語が "C-663" 1トークンで取れない場合に備え、行単位で結合も試みる。
    results: list[tuple[str, float, float]] = []
    n = len(data["text"])
    for i in range(n):
        txt = (data["text"][i] or "").strip().upper()
        if not txt:
            continue
        cand = normalize_mesh(txt)
        if MESH_RE.match(cand):
            x = data["left"][i] + data["width"][i] / 2
            y = data["top"][i] + data["height"][i] / 2
            results.append((cand, float(x), float(y)))
    return results


def positions_to_grid(positions: list[tuple[str, float, float]],
                      img_w: int, img_h: int,
                      n_cols: int, n_rows: int) -> dict[str, tuple[int, int]]:
    """ピクセル中心を絶対 col/row に量子化する。

    セル中心の起点は cell_w/2, cell_h/2（最西/最北セルの中心）と仮定。
    """
    cell_w = img_w / n_cols
    cell_h = img_h / n_rows
    mapping: dict[str, tuple[int, int]] = {}
    for mesh, x, y in positions:
        col = round((x - cell_w / 2) / cell_w)
        row = round((y - cell_h / 2) / cell_h)
        col = max(0, min(n_cols - 1, col))
        row = max(0, min(n_rows - 1, row))
        # 同一メッシュが複数 OCR された場合は最初を採用（重複は後段で確認）。
        mapping.setdefault(mesh, (col, row))
    return mapping


# 印字位置 -> セル中心 の系統オフセット（KMZ画像の格子線実測で確定）。
# 地図のメッシュ番号はセル左上寄りに印字されるため、OCR位置はセル中心より
# 左上にずれる。切片にこれを足してセル中心基準に補正する。
PRINT_TO_CENTER_DX = 32.05
PRINT_TO_CENTER_DY = 52.33


def fit_calibration() -> dict[str, float]:
    """OCRアンカーから col/row -> pixel(セル中心) の線形係数を求める。

    傾きは OCR 印字位置のフィット、切片は印字→セル中心オフセットで補正。
    返り値: {col_w_px, x0_px, row_h_px, y0_px, max_resid_px}
    col/row は build_grid の規則で算出する。
    """
    from .build_grid import MAJOR_COL_INDEX, MAJOR_ROW_BY_D2, ONES

    def colrow(mesh: str) -> tuple[int, int]:
        letter, num = mesh.split("-")
        d2, d1, d0 = int(num[0]), int(num[1]), int(num[2])
        dx, dy = ONES[d0]
        return MAJOR_COL_INDEX[(letter, d1)] * 2 + dx, MAJOR_ROW_BY_D2[d2] * 2 + dy

    cols, xs, rows, ys = [], [], [], []
    for mesh, (x, y) in OCR_ANCHORS_PX.items():
        c, r = colrow(mesh)
        cols.append(c); xs.append(x); rows.append(r); ys.append(y)

    # 単回帰（numpy 非依存）。
    def linfit(t, v):
        n = len(t)
        mt = sum(t) / n
        mv = sum(v) / n
        num = sum((t[i] - mt) * (v[i] - mv) for i in range(n))
        den = sum((t[i] - mt) ** 2 for i in range(n))
        a = num / den
        b = mv - a * mt
        return a, b

    col_w, x0_print = linfit(cols, xs)
    row_h, y0_print = linfit(rows, ys)
    max_resid = max(abs(col_w * cols[i] + x0_print - xs[i]) for i in range(len(cols)))
    # 印字位置基準の切片を、セル中心基準に補正。
    x0 = x0_print + PRINT_TO_CENTER_DX
    y0 = y0_print + PRINT_TO_CENTER_DY
    return {"col_w_px": col_w, "x0_px": x0, "row_h_px": row_h,
            "y0_px": y0, "max_resid_px": max_resid}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="KMZ画像OCR -> mesh対応表(画像実測)")
    p.add_argument("source", help="KMZ または 画像(PNG/JPG)")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--cols", type=int, default=DEFAULT_COLS)
    p.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    p.add_argument("--dump-positions", help="OCR生位置を CSV 出力（デバッグ用）")
    args = p.parse_args(argv)

    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        img_path = _load_image_path(Path(args.source), Path(td))
        img_w, img_h = Image.open(img_path).size
        positions = ocr_mesh_positions(img_path)

    print(f"OCR で得たメッシュ候補: {len(positions)} 個")
    if args.dump_positions:
        with open(args.dump_positions, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["mesh", "x_px", "y_px"])
            for mesh, x, y in sorted(positions):
                w.writerow([mesh, round(x, 1), round(y, 1)])

    mapping = positions_to_grid(positions, img_w, img_h, args.cols, args.rows)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mesh", "col", "row"])
        for mesh, (c, r) in sorted(mapping.items()):
            w.writerow([mesh, c, r])
    print(f"書き出し: {args.output}  ({len(mapping)} メッシュ, {args.cols}列x{args.rows}行)")
    print("⚠ OCR 結果です。必ず目視検証（grid_check.kml を画像に重ねる）で確認してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
