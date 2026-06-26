"""捕獲記録 CSV -> GeoJSON (RFC 7946) 変換。

入力 CSV（手起こし or OCR 補助で作成）の想定列（ヘッダ名）:
  serialNo, captureNo, species, hunterName, team, captureDate,
  method, areaName, mesh, quadrant, weightKg, lengthCm, sex, antler,
  fetusCount, estimatedAge
  （captureDate は和暦文字列。数値列は空欄可。fetusCount 空欄は 0。
   estimatedAge は「3〜4」等の範囲表記を文字列のまま保持。）

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
    "method", "areaName", "mesh", "quadrant", "sex", "antler", "estimatedAge",
]
INT_FIELDS = ["serialNo", "fetusCount"]
FLOAT_FIELDS = ["weightKg", "lengthCm"]

VALID_SPECIES = {"イノシシ", "シカ", "クマ"}
VALID_QUADRANTS = {"左上", "右上", "左下", "右下"}
VALID_SEX = {"オス", "メス"}
VALID_ANTLER = {"あり", "なし"}

# 値の許容範囲（手起こしの桁ミス・誤読を炙り出すための緩い上下限）。
WEIGHT_KG_RANGE = (1, 200)
LENGTH_CM_RANGE = (10, 300)
FETUS_COUNT_MAX = 12

# properties の出力順（仕様 Feature 例に準拠）。
PROP_ORDER = [
    "serialNo", "captureNo", "species", "hunterName", "team", "captureDate",
    "method", "areaName", "mesh", "quadrant", "weightKg", "lengthCm", "sex", "antler",
    "fetusCount", "estimatedAge",
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
    # 胎児頭数は空欄を 0 とみなす（頭数>0 で「有り」と解釈する仕様）。
    if raw.get("fetusCount") is None:
        raw["fetusCount"] = 0

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


def validate_csv(csv_path: str | Path, grid: MeshGrid) -> list[str]:
    """CSV を機械的に点検し、疑わしい行の警告メッセージ一覧を返す（空なら問題なし）。

    手起こし/OCR でありがちな誤りを炙り出す:
      - メッシュ番号が対応表に未登録 / 象限・性別・角が許容外
      - 体重・体長が数値でない、または異常値
      - 胎児頭数が数値でない、または過大
      - 捕獲番号(species+captureNo)の重複、通し番号の重複・飛び
    値の正誤そのものは判定できない（票との突き合わせは別途）。
    """
    warns: list[str] = []
    serials: list[int] = []
    seen_capture: dict[tuple[str, str], int] = {}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        sn_raw = _clean(row.get("serialNo"))
        sn = f"通し{sn_raw}" if sn_raw else "通し?"
        cap = _clean(row.get("captureNo"))
        tag = f"{sn} ({cap})" if cap else sn

        mesh = _clean(row.get("mesh"))
        quad = _clean(row.get("quadrant"))
        if mesh and mesh not in grid.mapping:
            warns.append(f"{tag}: 未登録メッシュ {mesh!r}")
        if quad and quad not in VALID_QUADRANTS:
            warns.append(f"{tag}: 不正な象限 {quad!r}（許容: {sorted(VALID_QUADRANTS)}）")
        if (mesh and not quad) or (quad and not mesh):
            warns.append(f"{tag}: mesh/quadrant の片方のみ（mesh={mesh!r} quadrant={quad!r}）")

        species = _clean(row.get("species"))
        if species and species not in VALID_SPECIES:
            warns.append(f"{tag}: 未知の種別 {species!r}")
        sex = _clean(row.get("sex"))
        if sex and sex not in VALID_SEX:
            warns.append(f"{tag}: 不正な性別 {sex!r}")
        antler = _clean(row.get("antler"))
        if antler and antler not in VALID_ANTLER:
            warns.append(f"{tag}: 不正な角 {antler!r}（許容: あり/なし）")

        # 数値範囲チェック（空欄は許容。非数値・範囲外を警告）。
        for field, rng, label in (
            ("weightKg", WEIGHT_KG_RANGE, "体重"),
            ("lengthCm", LENGTH_CM_RANGE, "体長"),
        ):
            raw = _clean(row.get(field))
            if raw is None:
                continue
            num = _to_number(raw)
            if num is None:
                warns.append(f"{tag}: {label}が数値でない {raw!r}")
            elif not (rng[0] <= num <= rng[1]):
                warns.append(f"{tag}: {label}が範囲外 {num}（想定 {rng[0]}〜{rng[1]}）")

        fc_raw = _clean(row.get("fetusCount"))
        if fc_raw is not None:
            n = _to_number(fc_raw, as_int=True)
            if n is None:
                warns.append(f"{tag}: 胎児頭数が数値でない {fc_raw!r}")
            elif n < 0 or n > FETUS_COUNT_MAX:
                warns.append(f"{tag}: 胎児頭数が異常 {n}（0〜{FETUS_COUNT_MAX}）")

        # 捕獲番号の重複（種別ごと）。
        if species and cap:
            key = (species, cap)
            if key in seen_capture:
                warns.append(
                    f"{tag}: 捕獲番号が重複（{species} {cap} は通し{seen_capture[key]}にも）")
            else:
                seen_capture[key] = sn_raw or "?"

        if sn_raw is not None:
            try:
                serials.append(int(sn_raw))
            except ValueError:
                warns.append(f"{tag}: 通し番号が数値でない {sn_raw!r}")

    # 通し番号の重複・飛びチェック。
    dup = {n for n in serials if serials.count(n) > 1}
    for n in sorted(dup):
        warns.append(f"通し{n}: 通し番号が重複")
    if serials:
        full = set(range(min(serials), max(serials) + 1))
        missing = sorted(full - set(serials))
        if missing:
            warns.append(f"通し番号の欠番: {missing}")

    return warns


def write_geojson(fc: dict[str, Any], out_path: str | Path) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
        f.write("\n")
