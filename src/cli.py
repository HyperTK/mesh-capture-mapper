"""コマンドライン: 捕獲記録 CSV -> GeoJSON。

使い方:
  python -m src.cli data/input/records.csv -o data/output/captures.geojson
  python -m src.cli records.csv            # 標準出力に書き出し
オプション:
  --grid PATH    メッシュ対応表 CSV（既定: data/reference/mesh_grid.csv）
  --strict       未解決メッシュ/象限・欠損でエラー停止（既定はスキップして報告）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .convert import convert_csv, validate_csv, write_geojson
from .grid import MeshGrid

DEFAULT_GRID = Path(__file__).resolve().parents[1] / "data" / "reference" / "mesh_grid.csv"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="捕獲記録CSV -> GeoJSON 変換")
    p.add_argument("input", help="捕獲記録 CSV")
    p.add_argument("-o", "--output", help="出力 GeoJSON（省略時は標準出力）")
    p.add_argument("--grid", default=str(DEFAULT_GRID), help="メッシュ対応表 CSV")
    p.add_argument("--strict", action="store_true", help="欠損・未解決でエラー停止")
    p.add_argument("--validate", action="store_true",
                   help="変換前にCSVを点検し、疑わしい行を一覧表示する")
    args = p.parse_args(argv)

    grid = MeshGrid.from_csv(args.grid)

    if args.validate:
        warns = validate_csv(args.input, grid)
        if warns:
            print(f"⚠ 点検で {len(warns)} 件の要確認:", file=sys.stderr)
            for w in warns:
                print(f"  - {w}", file=sys.stderr)
        else:
            print("✓ 点検: 問題は見つかりませんでした。", file=sys.stderr)

    fc, skipped = convert_csv(args.input, grid, strict=args.strict)

    if args.output:
        write_geojson(fc, args.output)
        print(f"書き出し: {args.output}  ({len(fc['features'])} features)", file=sys.stderr)
    else:
        json.dump(fc, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")

    if skipped:
        print(f"⚠ 変換できなかった行: {len(skipped)} 件（mesh/quadrant 欠損または未登録）",
              file=sys.stderr)
        for r in skipped[:10]:
            print(f"  - serialNo={r.get('serialNo')} mesh={r.get('mesh')!r} "
                  f"quadrant={r.get('quadrant')!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
