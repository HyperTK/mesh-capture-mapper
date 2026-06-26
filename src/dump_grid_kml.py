"""対応表の全メッシュを Google Earth 用 KML に書き出す（目視検証用）。

Google Earth では KMZ（ハンターマップ画像）がそのまま画像オーバーレイとして
表示される。この KML を重ねると、各セル枠・中心ラベルが画像の格子・メッシュ番号と
一致するか確認できる。

出力する要素:
  - 各メッシュのセル枠（半透明の矩形ポリゴン、枠線あり）
  - 各メッシュ中心の Placemark（name=mesh ラベル）

使い方:
  python -m src.dump_grid_kml -o data/output/grid_check.kml
  # Google Earth で KMZ を開き、この KML をドラッグして重ねる。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from .grid import MeshGrid

DEFAULT_GRID = Path(__file__).resolve().parents[1] / "data" / "reference" / "mesh_grid.csv"


def build_kml(grid: MeshGrid) -> str:
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    parts.append("<Document>")
    parts.append("<name>mesh grid check</name>")
    # セル枠スタイル: 太い赤枠＋薄い赤の塗り。KMZ画像に埋もれないよう
    # 塗りを少し入れ、線も太くして視認性を上げる。
    parts.append(
        '<Style id="cell">'
        "<LineStyle><color>ff0000ff</color><width>3.0</width></LineStyle>"
        "<PolyStyle><color>33000099</color><fill>1</fill><outline>1</outline></PolyStyle>"
        "</Style>"
    )
    # 中心ラベルスタイル。
    parts.append(
        '<Style id="center">'
        "<IconStyle><scale>0.4</scale></IconStyle>"
        "<LabelStyle><scale>0.7</scale></LabelStyle>"
        "</Style>"
    )

    for mesh, (col, row) in sorted(grid.mapping.items()):
        w, e, n, s = grid.cell_bounds(col, row)
        cx, cy = (w + e) / 2, (n + s) / 2
        name = escape(mesh)
        # セル枠ポリゴン。altitudeMode=clampToGround で地表（画像オーバーレイの上）に貼る。
        ring = f"{w},{n},0 {e},{n},0 {e},{s},0 {w},{s},0 {w},{n},0"
        parts.append(
            f"<Placemark><name>{name}</name><styleUrl>#cell</styleUrl>"
            f"<Polygon><altitudeMode>clampToGround</altitudeMode>"
            f"<outerBoundaryIs><LinearRing>"
            f"<coordinates>{ring}</coordinates>"
            f"</LinearRing></outerBoundaryIs></Polygon></Placemark>"
        )
        # 中心ラベル
        parts.append(
            f"<Placemark><name>{name}</name><styleUrl>#center</styleUrl>"
            f"<Point><coordinates>{cx:.6f},{cy:.6f},0</coordinates></Point>"
            f"</Placemark>"
        )

    parts.append("</Document></kml>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="対応表 -> 格子可視化 KML（Google Earth用）")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--grid", default=str(DEFAULT_GRID))
    args = p.parse_args(argv)
    grid = MeshGrid.from_csv(args.grid)
    Path(args.output).write_text(build_kml(grid), encoding="utf-8")
    print(f"書き出し: {args.output}  ({len(grid.mapping)} メッシュ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
