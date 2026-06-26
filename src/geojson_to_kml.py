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
import math
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

# 種ごとにピン色を変える（KMLは aabbggrr 順）。
SPECIES_COLOR = {
    "イノシシ": "ff0000ff",  # 赤
    "シカ": "ff00ff00",      # 緑
    "クマ": "ffff0000",      # 青
}
DEFAULT_COLOR = "ff00ffff"   # 黄（種不明）

# 同一座標（同一メッシュ＋象限）に重なるピンを小さな円状に散らす半径（度・緯度方向）。
# 象限は1/4セル（緯度約0.0105°）なので、その内側に十分収まる小さめの値。
# 経度方向は 1/cos(lat) で割って画面上で正円に見えるよう補正する。
JITTER_RADIUS_DEG = 0.0018


def _jittered(lon: float, lat: float, idx: int, count: int) -> tuple[float, float]:
    """同一座標に count 個重なるうちの idx 番目を、中心まわりの小円上に配置する。

    count==1 なら中心のまま。座標は象限中心からのずれであり、データの真値は
    GeoJSON 側（象限中心）に保持される。表示分離のための KML 専用処理。
    """
    if count <= 1:
        return lon, lat
    angle = 2.0 * math.pi * idx / count
    dlat = JITTER_RADIUS_DEG * math.sin(angle)
    coslat = math.cos(math.radians(lat)) or 1.0
    dlon = JITTER_RADIUS_DEG * math.cos(angle) / coslat
    return lon + dlon, lat + dlat


# GeoJSON properties は convert 側で既に日本語キー・定義順になっている。
# 種別・メッシュ番号・メッシュ内位置はピン名/色分けに使う日本語キー。
SPECIES_KEY = "種別"
NAME_KEYS = ("捕獲番号", "メッシュ番号", "メッシュ内位置")


def _desc(props: dict) -> str:
    # properties をそのまま日本語キーで表示する。内部フラグ（_で始まる）は除く。
    # name は地図ツール用の慣例キー（捕獲者と同値）なので説明文では重複を避け除外。
    # 胎児頭数は 0 も意味があるため None 以外は表示する。
    lines = [f"{k}: {v}" for k, v in props.items()
             if k != "name" and not k.startswith("_") and v is not None]
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

    # 同一座標（同一メッシュ＋象限）のピンは重なって見えないため、出現順に
    # インデックスを振って小円状に散らす。まず座標ごとの件数を数える。
    point_feats = [f for f in fc.get("features", [])
                   if (f.get("geometry") or {}).get("type") == "Point"]
    coord_total: dict[tuple[float, float], int] = defaultdict(int)
    for f in point_feats:
        c = tuple(f["geometry"]["coordinates"][:2])
        coord_total[c] += 1
    coord_seen: dict[tuple[float, float], int] = defaultdict(int)

    for feat in point_feats:
        geom = feat["geometry"]
        lon, lat = geom["coordinates"][:2]
        key = (lon, lat)
        idx = coord_seen[key]
        coord_seen[key] += 1
        lon, lat = _jittered(lon, lat, idx, coord_total[key])
        props = feat.get("properties", {})
        color = SPECIES_COLOR.get(props.get(SPECIES_KEY), DEFAULT_COLOR)
        name = " / ".join(
            str(props.get(k)) for k in NAME_KEYS
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
