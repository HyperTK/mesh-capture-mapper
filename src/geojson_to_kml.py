"""捕獲記録 GeoJSON を Google Earth 用 KML に変換する（目視検証用）。

convert.py が出力した captures.geojson / sample.geojson を Google Earth で
KMZ（ハンターマップ画像）や grid_check.kml と一緒に重ねるために使う。

各 Feature を Point Placemark にし、name は「捕獲番号 / メッシュ / 象限」、
説明に主要 properties を入れる。

使い方:
  python -m src.geojson_to_kml data/output/sample.geojson -o data/output/sample.kml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

# 種ごとにピン色を変える（KMLは aabbggrr 順）。
SPECIES_COLOR = {
    "イノシシ": "ff0000ff",  # 赤
    "シカ": "ff00ff00",      # 緑
    "クマ": "ffff0000",      # 青
}
DEFAULT_COLOR = "ff00ffff"   # 黄（種不明）


def _desc(props: dict) -> str:
    keys = ["serialNo", "captureNo", "species", "team", "captureDate",
            "method", "areaName", "mesh", "quadrant", "weightKg", "lengthCm",
            "sex", "antler"]
    lines = [f"{k}: {props.get(k)}" for k in keys if props.get(k) is not None]
    return escape("\n".join(lines))


def build_kml(fc: dict) -> str:
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    parts.append("<Document><name>captures</name>")
    for color in set(SPECIES_COLOR.values()) | {DEFAULT_COLOR}:
        parts.append(
            f'<Style id="s{color}">'
            f"<IconStyle><color>{color}</color><scale>1.0</scale></IconStyle>"
            f"</Style>"
        )

    for feat in fc.get("features", []):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        props = feat.get("properties", {})
        color = SPECIES_COLOR.get(props.get("species"), DEFAULT_COLOR)
        name = " / ".join(
            str(props.get(k)) for k in ("captureNo", "mesh", "quadrant")
            if props.get(k) is not None
        ) or "(no name)"
        parts.append(
            f"<Placemark><name>{escape(name)}</name>"
            f"<styleUrl>#s{color}</styleUrl>"
            f"<description>{_desc(props)}</description>"
            f"<Point><coordinates>{lon},{lat},0</coordinates></Point>"
            f"</Placemark>"
        )
    parts.append("</Document></kml>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="捕獲GeoJSON -> KML（Google Earth用）")
    p.add_argument("input", help="captures.geojson")
    p.add_argument("-o", "--output", required=True)
    args = p.parse_args(argv)
    fc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(build_kml(fc), encoding="utf-8")
    n = sum(1 for f in fc.get("features", [])
            if (f.get("geometry") or {}).get("type") == "Point")
    print(f"書き出し: {args.output}  ({n} ピン)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
