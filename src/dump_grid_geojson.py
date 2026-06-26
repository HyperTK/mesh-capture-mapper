"""対応表の全メッシュをグリッド可視化用 GeoJSON に書き出す（目視検証用）。

geojson.io や QGIS で KMZ のハンターマップ画像に重ね、
各メッシュのセル枠・中心ラベルが格子と一致するか確認するために使う。

出力:
  - points: 各メッシュのセル中心（label=mesh）
  - polygons: 各メッシュのセル枠（矩形）
使い方:
  python -m src.dump_grid_geojson -o data/output/grid_check.geojson
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .grid import MeshGrid

DEFAULT_GRID = Path(__file__).resolve().parents[1] / "data" / "reference" / "mesh_grid.csv"


def build(grid: MeshGrid) -> dict:
    features = []
    for mesh, (col, row) in grid.mapping.items():
        w, e, n, s = grid.cell_bounds(col, row)
        cx, cy = (w + e) / 2, (n + s) / 2
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(cx, 6), round(cy, 6)]},
            "properties": {"mesh": mesh, "kind": "center", "col": col, "row": row},
        })
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [w, n], [e, n], [e, s], [w, s], [w, n],
                ]],
            },
            "properties": {"mesh": mesh, "kind": "cell"},
        })
    return {"type": "FeatureCollection", "features": features}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="対応表 -> 格子可視化 GeoJSON")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--grid", default=str(DEFAULT_GRID))
    args = p.parse_args(argv)
    grid = MeshGrid.from_csv(args.grid)
    fc = build(grid)
    Path(args.output).write_text(
        json.dumps(fc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"書き出し: {args.output}  ({len(grid.mapping)} メッシュ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
