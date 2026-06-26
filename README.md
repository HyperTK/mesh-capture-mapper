# mesh-capture-mapper

雫石町 有害駆除（イノシシ・シカ・クマ）の捕獲記録を、**メッシュ番号＋象限**から
緯度経度に変換し、**GeoJSON（捕獲地点）** を生成するツール。

データは町の隊員全員の共有成果として、着脱可能な独立ファイル（GeoJSON）で持つ。
DB（Firestore等）には保存しない。

---

## 全体の流れ

```
[捕獲記録PDF(スキャン)]            [ハンターマップ KMZ]
        │                                 │
   OCR補助 or 手起こし          画像実測でメッシュ格子規則を確定
        │                                 │
        ▼                                 ▼
   records CSV  ──────┐        data/reference/mesh_grid.csv
                      │        （mesh → col,row 対応表 + 四隅座標）
                      ▼                    │
              [src/convert.py] ◀───────────┘
                      │
                      ▼
            captures.geojson (RFC 7946)
```

処理は2フェーズ:

- **フェーズA（一度きり・確定済み）**: KMZ画像からメッシュ格子規則を確定し、
  `mesh → (col, row)` 対応表 `data/reference/mesh_grid.csv` を作る。
- **フェーズB（繰り返し）**: 捕獲記録 CSV ＋ 対応表 → GeoJSON 変換。

---

## メッシュ格子規則（フェーズAの結論）

KMZ画像（`overlay`, 1116×2061px）を実測して確定した。
メッシュ番号 `<英字>-<3桁数字>`（例: `C-374`）は独自の再帰分割コード:

| 桁 | 意味 |
|----|------|
| 一の位 `d0` | 2×2セル内の位置 `{3:左上, 4:右上, 1:左下, 2:右下}` |
| 十の位 `d1` ＋ 英字 | 東西の連続インデックス（西→東。例: `C-05x→C-06x→C-07x→D-00x`） |
| 百の位 `d2` | 南北の連続インデックス（北→南で `6→5→4→3→2→1→0`） |

- 対応表は C系〜D系を覆うが、**画像（1116px幅）に収まる col 0〜6 の 98メッシュ**を採用する。
  較正は col 0〜6 のアンカーで取得しており、col≥7（D系の東端）は画像右端の外へ
  外挿され格子が歪むため対応表から除外している（詳細は「既知の注意点」）。
- 純粋な数式デコードは大ブロック境界で非連続になり破綻し得るため、
  **対応表 CSV を真実の源**とする（仕様の「対応表方式」）。
- 対応表は `src/build_grid.py` が規則生成し、画像実測アンカーで検証して作った。

### 座標の算出（ピクセルアンカー方式）

四隅座標を「総セル数で等分」すると、**画像端がセルの途中で切れている**ため
分母が非整数となり格子が画像とズレる（実際にズレた）。これを避けるため、
**KMZ画像に印字されたメッシュ番号のピクセル位置を実測**して座標化する:

1. OCR/実測で複数メッシュの印字ピクセル中心 (x, y) を取得。
2. `col/row`（規則由来）とピクセルを最小二乗フィットし、印字→セル中心オフセットで補正:
   ```
   x = 151.995 * col + 105.44   (列幅 ≈ 152.0px)
   y = 131.079 * row + 128.84   (行高 ≈ 131.1px)
   ```
   （`src/build_grid_from_image.py::fit_calibration` で傾きを再現可能。
    切片は格子線実測でセル中心基準に補正済み。
    係数は `src/grid.GridCalibration` の既定値）
3. 四隅 bbox（rotation=0, 北が上, 画像 1116×2061px）で px → 緯度経度:
   ```
   lon = west  + (east  - west ) * (x / 1116)
   lat = north - (north - south) * (y / 2061)
   ```
4. セルを 2×2 に分割し、象限の中心を採る（位置精度は **セルの1/4**）。

ピン座標は **おおよそのエリア代表点**であり、厳密な捕獲地点ではない。

> 検証: `tests/test_grid.py` の `test_cell_top_matches_grid_line` /
> `test_cell_left_matches_grid_line` が、計算したセル境界が実測の格子線と
> 一致することを確認する。`test_all_cells_inside_image` で全セルが画像内に
> 収まる（col≥7 の外挿が混入しない）ことも検証する。

---

## 入力 CSV の形式

ヘッダ:

```
serialNo,captureNo,species,hunterName,team,captureDate,method,
areaName,mesh,quadrant,weightKg,lengthCm,sex,antler,fetusCount,estimatedAge
```

- `captureDate` は和暦文字列（例: `令和8年4月21日`）。西暦 ISO 8601 に自動変換。
- `mesh`（例 `C-374`）, `quadrant`（`左上/右上/左下/右下`）は座標の根拠として必須。
- 数値列・空欄は `null` になる。`fetusCount`（胎児頭数）の空欄は `0`（頭数>0 で「有り」とみなす）。
- `estimatedAge`（推定年齢）は `3〜4` のような範囲表記を文字列のまま保持する。
- **`data/input/` と `data/output/` は捕獲者名など個人情報を含み得るため Git 追跡対象外**
  （`.gitignore` で除外）。CSV はローカルに置いて使う。`data/reference/` のみ追跡する。

---

## 使い方

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .              # Pillow のみ
pip install -e ".[ocr,dev]"   # OCR補助・テストも使う場合

# 捕獲記録CSV -> GeoJSON
python -m src.cli data/input/records.csv -o data/output/captures.geojson

# 変換前に CSV を点検（未登録メッシュ・象限/性別/角の不正・数値異常・
# 捕獲番号重複・通し番号の重複/欠番を一覧表示。手起こし/OCR の誤りを炙り出す）
python -m src.cli data/input/records.csv --validate -o data/output/captures.geojson

# 格子可視化（目視検証用）GeoJSON
python -m src.dump_grid_geojson -o data/output/grid_check.geojson

# OCR下書き（要・目視修正。poppler/tesseract が別途必要）
python -m src.ocr_assist 捕獲記録.pdf -o data/input/ocr_draft.txt
```

---

## 出力 GeoJSON

- RFC 7946 FeatureCollection。`geometry: Point`、`coordinates = [経度, 緯度]`。
- **1 Feature = 1 捕獲記録**。`properties` に元データを保持（`mesh`/`quadrant` 必須）。
- 同一（mesh＋象限）の重複は同一座標になるが、GeoJSON では**無理に散らさない**
  （座標は象限中心＝データの真値）。各記録を残し、表示側でクラスタ表示する前提。
- 目視検証用の KML（`geojson_to_kml`）では、重なるピンを象限内で小円状に散らして
  件数を視認できるようにする（表示専用。GeoJSON の座標は変更しない）。

---

## 目視検証の手順（Google Earth）

geojson.io は KMZ の画像オーバーレイを描画できない（四隅のポリゴンしか出ない）。
画像と格子を突き合わせるには **Google Earth** を使う。KMZ はそのまま画像
オーバーレイとして表示され、重ねる格子・ピンは KML に変換して読み込む。

1. 検証用 KML を生成（GeoJSON ではなく KML を使う）:
   ```bash
   python -m src.dump_grid_kml -o data/output/grid_check.kml          # 98メッシュの枠＋ラベル
   python -m src.geojson_to_kml data/output/sample.geojson -o data/output/sample.kml
   ```
   `geojson_to_kml` の出力は、各ピンの説明文を日本語ラベル化し、捕獲者・胎児頭数・
   推定年齢を含む。種別ごとに色分けし、同一座標のピンは小円状に散らす。
2. Google Earth（[Web版](https://earth.google.com/web/) かデスクトップ版）で、
   `有害駆除資料/iwate_shizukuishi_hunter_map.kmz` を開く（画像が地図上に表示される）。
3. `grid_check.kml` を読み込んで重ね、各セル枠・中心ラベルが画像の格子線・
   印字メッシュ番号と一致するか確認する。
4. `sample.kml`（実データなら `captures.geojson` を KML 変換したもの）も重ね、
   数件のピンが正しい格子・象限に落ちるか確認する。

> 参考: ラフな位置確認だけなら、`src/dump_grid_geojson.py` が出す GeoJSON を
> geojson.io / QGIS で開いてもよい（ただし KMZ 画像との重ね合わせは不可）。
> 厳密な格子一致の検証は Google Earth か QGIS（KMZ をラスタ読み込み）で行う。

---

## 既知の注意点

- **令和8年 = 2026年**（実暦）。元仕様本文の「令和N年 = 2017 + N」は誤りで、
  仕様の Feature 例（`2026-04-21`）と一致する `令和N年 = 2018 + N` を採用している。
  （`src/wareki.py` 参照）
- **col≥7（D系の東端）は対応表から除外**。較正は col 0〜6 のアンカーで取得しており、
  col≥7 をそのまま外挿するとセル中心が画像右端（1116px）を超え、bbox の外へ
  外挿されて格子が東に伸び縦長に歪む。D系東端を座標化するには、その領域を含む
  別のハンターマップ画像とその LatLonBox が必要。
- 画像最下段の `A-7xx` 等は隣接図郭の写り込みで、主図郭の連続格子から外れる。
  これらは対応表に未登録。実データに現れたら個別に画像実測して追加する。
- 未登録メッシュ・象限欠損は変換時にスキップされ、件数が警告表示される（`--strict` で停止）。
  投入前に `--validate` で CSV を点検すると、手起こし/OCR の誤り（未登録メッシュ、
  象限・性別・角の不正、数値異常、捕獲番号重複、通し番号の欠番）を炙り出せる。
  ただし「値そのものの正誤＝元票との照合」は別途必要。
- 文字コードは UTF-8。

## スコープ外

- アプリ（Flutter/Firestore）への保存・取り込み。
- GeoJSON の配置場所（同梱／リモート）。
