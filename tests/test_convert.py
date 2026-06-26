from pathlib import Path

import pytest

from src.convert import convert_csv, record_to_feature, validate_csv
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
    # 出力 properties は日本語キー。
    p = feat["properties"]
    assert p["捕獲年月日"] == "2026-04-21"
    assert p["体重kg"] == 50 and isinstance(p["体重kg"], int)
    assert p["メッシュ番号"] == "C-374" and p["メッシュ内位置"] == "右下"


def test_empty_fields_become_null(grid):
    row = {
        "serialNo": "2", "captureNo": "B-1", "species": "クマ",
        "hunterName": "", "team": "御所第3班", "captureDate": "令和7年11月2日",
        "method": "くくり罠", "areaName": "御明神", "mesh": "C-663",
        "quadrant": "左上", "weightKg": "", "lengthCm": "", "sex": "オス", "antler": "",
    }
    feat = record_to_feature(row, grid)
    p = feat["properties"]
    assert p["体重kg"] is None
    assert p["体長cm"] is None
    assert p["角"] is None  # 空文字でなく null


def test_missing_mesh_is_skipped(grid):
    fc, skipped = convert_csv(SAMPLE, grid)
    assert len(skipped) == 1
    assert skipped[0]["serialNo"] == "9"
    # sample は 5 行中 4 件が変換成功
    assert len(fc["features"]) == 4


def test_property_order(grid):
    # 出力 properties は日本語キーで、定義順に並ぶ。
    fc, _ = convert_csv(SAMPLE, grid)
    keys = list(fc["features"][0]["properties"].keys())
    assert keys[:4] == ["通し番号", "捕獲番号", "種別", "捕獲者"]


def test_duplicate_mesh_quadrant_same_point_kept(grid):
    # 同一(mesh+quadrant)の2記録は同一座標で、両方とも残る（散らさない）。
    fc, _ = convert_csv(SAMPLE, grid)
    c374 = [f for f in fc["features"]
            if f["properties"]["メッシュ番号"] == "C-374"
            and f["properties"]["メッシュ内位置"] == "右下"]
    assert len(c374) == 2
    assert c374[0]["geometry"]["coordinates"] == c374[1]["geometry"]["coordinates"]


def test_validate_clean_real_data(grid):
    # 修正済みの実データは点検で警告ゼロ。
    real = ROOT / "data" / "input" / "capture_records.csv"
    assert validate_csv(real, grid) == []


def test_validate_catches_errors(grid, tmp_path):
    csv_text = (
        "serialNo,captureNo,species,mesh,quadrant,weightKg,fetusCount\n"
        "1,S-1,イノシシ,Z-999,左下,30,0\n"          # 未登録メッシュ
        "1,S-1,イノシシ,C-374,まんなか,9000,99\n"   # 通し重複+象限不正+体重範囲外+胎児異常+捕獲番号重複
        "3,S-3,ツキノワ,C-374,左下,abc,0\n"          # 種別不正+体重非数値+欠番(2)
    )
    p = tmp_path / "broken.csv"
    p.write_text(csv_text, encoding="utf-8")
    warns = "\n".join(validate_csv(p, grid))
    assert "未登録メッシュ" in warns
    assert "不正な象限" in warns
    assert "体重が範囲外" in warns
    assert "胎児頭数が異常" in warns
    assert "捕獲番号が重複" in warns
    assert "未知の種別" in warns
    assert "体重が数値でない" in warns
    assert "通し番号が重複" in warns
    assert "欠番" in warns
