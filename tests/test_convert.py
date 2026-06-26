from pathlib import Path

import pytest

from src.convert import convert_csv, record_to_feature
from src.grid import MeshGrid
from src.wareki import wareki_to_iso

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference" / "mesh_grid.csv"
SAMPLE = ROOT / "data" / "input" / "sample_records.csv"


@pytest.fixture(scope="module")
def grid():
    return MeshGrid.from_csv(REF)


def test_wareki_reiwa8_is_2026():
    # Feature 例の captureDate と整合: 令和8年4月21日 = 2026-04-21
    assert wareki_to_iso("令和8年4月21日") == "2026-04-21"


def test_wareki_gannen():
    assert wareki_to_iso("令和元年5月1日") == "2019-05-01"


def test_wareki_invalid_returns_none():
    assert wareki_to_iso("") is None
    assert wareki_to_iso("不明") is None
    assert wareki_to_iso(None) is None


def test_feature_matches_spec_shape(grid):
    row = {
        "serialNo": "6", "captureNo": "S-374", "species": "イノシシ",
        "hunterName": "", "team": "御所第1班", "captureDate": "令和8年4月21日",
        "method": "くくり罠", "areaName": "西安庭第3地割", "mesh": "C-374",
        "quadrant": "右下", "weightKg": "50", "lengthCm": "115",
        "sex": "メス", "antler": "あり",
    }
    feat = record_to_feature(row, grid)
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    lon, lat = feat["geometry"]["coordinates"]
    # [経度, 緯度] の順で bbox 内
    assert 140.60895931 <= lon <= 141.06817802
    assert 39.28291197 <= lat <= 39.94402642
    p = feat["properties"]
    assert p["captureDate"] == "2026-04-21"
    assert p["weightKg"] == 50 and isinstance(p["weightKg"], int)
    assert p["mesh"] == "C-374" and p["quadrant"] == "右下"


def test_empty_fields_become_null(grid):
    row = {
        "serialNo": "2", "captureNo": "B-1", "species": "クマ",
        "hunterName": "", "team": "御所第3班", "captureDate": "令和7年11月2日",
        "method": "くくり罠", "areaName": "御明神", "mesh": "C-663",
        "quadrant": "左上", "weightKg": "", "lengthCm": "", "sex": "オス", "antler": "",
    }
    feat = record_to_feature(row, grid)
    p = feat["properties"]
    assert p["weightKg"] is None
    assert p["lengthCm"] is None
    assert p["antler"] is None  # 空文字でなく null


def test_missing_mesh_is_skipped(grid):
    fc, skipped = convert_csv(SAMPLE, grid)
    assert len(skipped) == 1
    assert skipped[0]["serialNo"] == "9"
    # sample は 5 行中 4 件が変換成功
    assert len(fc["features"]) == 4


def test_property_order(grid):
    fc, _ = convert_csv(SAMPLE, grid)
    keys = list(fc["features"][0]["properties"].keys())
    assert keys[:4] == ["serialNo", "captureNo", "species", "hunterName"]


def test_duplicate_mesh_quadrant_same_point_kept(grid):
    # 同一(mesh+quadrant)の2記録は同一座標で、両方とも残る（散らさない）。
    fc, _ = convert_csv(SAMPLE, grid)
    c374 = [f for f in fc["features"]
            if f["properties"]["mesh"] == "C-374"
            and f["properties"]["quadrant"] == "右下"]
    assert len(c374) == 2
    assert c374[0]["geometry"]["coordinates"] == c374[1]["geometry"]["coordinates"]
