"""捕獲記録 CSV -> GeoJSON (RFC 7946) 変換。

入力 CSV（手起こし or OCR 補助で作成）の想定列（ヘッダ名）:
  serialNo, captureNo, species, hunterName, team, captureDate,
  method, areaName, mesh, quadrant, weightKg, lengthCm, sex, antler
  （captureDate は和暦文字列。数値列は空欄可。）

出力:
  FeatureCollection。1 Feature = 1 捕獲記録。
  geometry: Point, coordinates = [経度, 緯度]。
  properties に元データを保持し、mesh / quadrant を必ず残す。
  同一(mesh+quadrant)は同一座標になり得るが、無理に散らさず各記録を残す
  （表示側でクラスタ/件数集約する前提）。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .grid import MeshGrid, SHIZUKUISHI_BBOX
from .wareki import wareki_to_iso

# CSV 列 -> properties キー。値はそのまま文字列で持つもの。
STR_FIELDS = [
    "captureNo", "species", "hunterName", "team",
    "method", "areaName", "mesh", "quadrant", "sex", "antler",
]
INT_FIELDS = ["serialNo"]
FLOAT_FIELDS = ["weightKg", "lengthCm"]

VALID_SPECIES = {"イノシシ", "シカ", "クマ"}

# properties の出力順（仕様 Feature 例に準拠）。
PROP_ORDER = [
    "serialNo", "captureNo", "species", "hunterName", "team", "captureDate",
    "method", "areaName", "mesh", "quadrant", "weightKg", "lengthCm", "sex", "antler",
]


def _clean(value: str | None) -> str | None:
    """空文字・空白のみは None に。それ以外は trim した文字列。"""
    if value is None:
        return None
    v = value.strip()
    return v if v else None


def _to_number(value: str | None, as_int: bool = False) -> float | int | None:
    v = _clean(value)
    if v is None:
        return None
    # 全角数字・単位混入を緩く除去
    v = v.translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    v = v.replace(",", "")
    m = "".join(ch for ch in v if ch.isdigit() or ch in ".-")
    if m in ("", "-", "."):
        return None
    try:
        num = float(m)
    except ValueError:
        return None
    if as_int:
        return int(num)
    # 整数値（50.0 等）は int で返し、小数があるときだけ float。
    return int(num) if num.is_integer() else num


def record_to_feature(row: dict[str, str], grid: MeshGrid,
                      strict: bool = False) -> dict[str, Any] | None:
    """CSV 1 行を GeoJSON Feature に変換。座標が引けない場合の扱いは strict で制御。

    strict=False: メッシュ/象限が未解決なら None を返す（スキップ）。
    strict=True : 例外を送出。
    """
    raw: dict[str, Any] = {}
    for f in STR_FIELDS:
        raw[f] = _clean(row.get(f))
    for f in INT_FIELDS:
        raw[f] = _to_number(row.get(f), as_int=True)
    for f in FLOAT_FIELDS:
        raw[f] = _to_number(row.get(f))
    raw["captureDate"] = wareki_to_iso(row.get("captureDate"))

    # properties は仕様の Feature 例に沿った順序で並べる。
    props: dict[str, Any] = {k: raw.get(k) for k in PROP_ORDER}

    # species の正規化チェック（不正値はそのまま残しつつ警告対象に）
    if props["species"] not in VALID_SPECIES:
        props["_speciesWarning"] = True

    mesh = props["mesh"]
    quadrant = props["quadrant"]
    if not mesh or not quadrant:
        if strict:
            raise ValueError(f"mesh/quadrant 欠損: serialNo={props.get('serialNo')}")
        return None
    try:
        lon, lat = grid.point(mesh, quadrant)
    except KeyError as e:
        if strict:
            raise
        # 未解決メッシュ/象限は geometry null で残す案もあるが、
        # 仕様は座標必須なのでスキップし呼び出し側で件数報告する。
        return None

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": props,
    }


def convert_csv(csv_path: str | Path, grid: MeshGrid,
                strict: bool = False) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """CSV を読み、FeatureCollection と「変換できなかった行」のリストを返す。"""
    features: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            feat = record_to_feature(row, grid, strict=strict)
            if feat is None:
                skipped.append(row)
            else:
                features.append(feat)
    fc = {"type": "FeatureCollection", "features": features}
    return fc, skipped


def write_geojson(fc: dict[str, Any], out_path: str | Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
        f.write("\n")
