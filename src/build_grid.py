"""画像実測アンカーから主図郭の対応表を構築し、ローカル規則で全セルを埋める。

確定した規則（KMZ画像実測）:
- 一の位 d0: 2x2内 {3:(W,N),4:(E,N),1:(W,S),2:(E,S)}  dx東+, dy南+
- 十の位 d1 + 英字: 東西の連続インデックス。
    例: C-05x | C-06x | C-07x | D-00x | D-01x ... と東へ。
    つまり「大列(major col)」= (英字, 十の位) のペアを東順に並べたもの。
- 百の位 d2: 南北の連続インデックス。北→南で 6,5,4,3,2,1,0 と単調減少。
    「大行(major row)」= d2 を北から 6,5,4,3,2,1,0 の順に並べたもの。
各 major セルは 2x2 の実セルを持つ（d0 の dx,dy）。
"""
import csv

# ---- 実測アンカー（行=北から、列=西から の相対major座標で記録）----
# major row: d2 値（北6 → 南0）
MAJOR_ROW_BY_D2 = {6: 0, 5: 1, 4: 2, 3: 3, 2: 4, 1: 5, 0: 6}  # C系主図郭の7大行

# major col: (letter, d1) を東順に。実測:
#   C-05x, C-06x, C-07x, D-00x, D-01x ... 西→東
# 左端が C-05x（最西）。十の位 5,6,7 → 次英字 D の 0,1,...
# 観察された西端は C-05x（大仙市側）、東端は D-00x 付近。
MAJOR_COL_ORDER = [
    ("C", 5), ("C", 6), ("C", 7),
    ("D", 0), ("D", 1),
]
MAJOR_COL_INDEX = {pair: i for i, pair in enumerate(MAJOR_COL_ORDER)}

ONES = {3: (0, 0), 4: (1, 0), 1: (0, 1), 2: (1, 1)}  # d0 -> (dx,dy)


def build():
    rows = []
    for (letter, d1), mcol in MAJOR_COL_INDEX.items():
        for d2, mrow in MAJOR_ROW_BY_D2.items():
            for d0, (dx, dy) in ONES.items():
                mesh = f"{letter}-{d2}{d1}{d0}"
                col = mcol * 2 + dx
                row = mrow * 2 + dy
                rows.append((mesh, col, row))
    rows.sort()
    return rows


# ---- 実測点での検証 ----
OBSERVED = {
    "C-663": (0, 0), "C-664": (1, 0), "C-673": (2, 0), "C-674": (3, 0),
    "C-661": (0, 1), "C-662": (1, 1), "C-671": (2, 1), "C-672": (3, 1),
    "C-563": (0, 2), "C-564": (1, 2), "C-573": (2, 2), "C-574": (3, 2),
    "C-374": (3, 6), "C-373": (2, 6),
    "D-603": (4, 0), "D-601": (4, 1), "D-503": (4, 2), "D-501": (4, 3),
    "C-053": (-2, 12), "C-054": (-1, 12), "C-063": (0, 12), "C-064": (1, 12),
    "C-051": (-2, 13), "C-052": (-1, 13), "C-061": (0, 13), "C-062": (1, 13),
}


def verify(rows):
    m = {mesh: (c, r) for mesh, c, r in rows}
    # OBSERVED は q1左上(C-663)を(0,0)とした相対。build()は MAJOR_COL_ORDER 西端を0とする絶対。
    # オフセットを C-663 で合わせる。
    if "C-663" not in m:
        return ["C-663 が生成表にない"]
    ox = m["C-663"][0] - OBSERVED["C-663"][0]
    oy = m["C-663"][1] - OBSERVED["C-663"][1]
    errs = []
    for mesh, (oc, orow) in OBSERVED.items():
        if mesh not in m:
            errs.append(f"{mesh}: 生成表に存在しない")
            continue
        gc, gr = m[mesh]
        if (gc - ox, gr - oy) != (oc, orow):
            errs.append(f"{mesh}: 生成{(gc-ox,gr-oy)} != 実測{(oc,orow)}")
    return errs


if __name__ == "__main__":
    rows = build()
    errs = verify(rows)
    print(f"生成セル数: {len(rows)}")
    if errs:
        print("検証: 不一致あり")
        for e in errs:
            print("  -", e)
    else:
        print("検証: 全実測点と一致 ✓")
        # 0起点に正規化して出力
        minc = min(c for _, c, _ in rows)
        minr = min(r for _, _, r in rows)
        norm = [(mesh, c - minc, r - minr) for mesh, c, r in rows]
        with open("mesh_grid_full.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["mesh", "col", "row"])
            w.writerows(norm)
        print(f"  cols 0..{max(c for _,c,_ in norm)}  rows 0..{max(r for _,_,r in norm)}")
