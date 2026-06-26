"""メッシュ番号 -> (col, row) を「規則」で生成し、対応表 CSV を作るためのモジュール。

KMZ画像の実測で確定した階層エンコード規則:
  ラベル `<英字A..>-<d2 d1 d0>`
    - 一の位 d0: 2x2 セル内の位置  {3:左上(W,N), 4:右上(E,N), 1:左下(W,S), 2:右下(E,S)}
    - 十の位 d1: 東西の「2セル束」インデックス（西→東で増加）
    - 百の位 d2: 南北の「2セル束」インデックス（北→南で変化）
    - 英字     : 東西の大ブロック（A→B→C→D で東へ）

注意:
  大ブロック境界で十・百の位が非連続に繰り上がる箇所が観察されている。
  そのため本モジュールが生成した対応表は「真実」ではなく「たたき台」であり、
  必ず KMZ 画像と突き合わせて検証・補正する（仕様の最重要事項）。
  検証で確定した対応表 CSV が src/grid.MeshGrid の真実の源になる。

このモジュールは規則をコードで明示し、画像実測点と照合する検証関数を提供する。
規則が全域で成り立つと確認できれば対応表生成に使い、
破綻するセルだけ手実測で上書きする運用を想定する。
"""

from __future__ import annotations

from .grid import normalize_mesh

# 一の位 -> 2x2 内オフセット (dx 東+, dy 南+)
ONES_OFFSET = {3: (0, 0), 4: (1, 0), 1: (0, 1), 2: (1, 1)}

# 画像実測で読み取った検証用の格子（行 row: 北から 0,1,2,... / 列 col: 西から 0,1,...）。
# q1 ブロック左上を (col=0,row=0) とした相対座標。
# ここを「真実」として規則の自己無矛盾を検証する。
OBSERVED = {
    # row 0 (最北)
    "C-663": (0, 0), "C-664": (1, 0), "C-673": (2, 0), "C-674": (3, 0), "D-603": (4, 0),
    # row 1
    "C-661": (0, 1), "C-662": (1, 1), "C-671": (2, 1), "C-672": (3, 1), "D-601": (4, 1),
    # row 2
    "C-563": (0, 2), "C-564": (1, 2), "C-573": (2, 2), "C-574": (3, 2), "D-503": (4, 2),
    # row 3
    "C-561": (0, 3), "C-562": (1, 3), "C-571": (2, 3), "C-572": (3, 3), "D-501": (4, 3),
}


def decode_ones(mesh: str) -> tuple[int, int]:
    """一の位から 2x2 セル内オフセット (dx, dy) を返す。"""
    num = normalize_mesh(mesh).split("-")[1]
    return ONES_OFFSET[int(num[2])]


def verify_against_observed() -> list[str]:
    """OBSERVED 内で「2セル束（十・百の位ペア）と一の位」の整合を検証する。

    返り値: 不整合メッセージのリスト（空なら自己無矛盾）。
    """
    errors: list[str] = []
    # 同一の十の位・百の位を共有するラベル群が、2x2 ブロックを成すか確認。
    groups: dict[tuple[str, int, int], list[str]] = {}
    for mesh in OBSERVED:
        letter, num = normalize_mesh(mesh).split("-")
        d2, d1 = int(num[0]), int(num[1])
        groups.setdefault((letter, d2, d1), []).append(mesh)

    for key, members in groups.items():
        base_cols = {OBSERVED[m][0] for m in members}
        base_rows = {OBSERVED[m][1] for m in members}
        # 2x2 ブロックなら col は隣接2値・row も隣接2値に収まる
        if len(base_cols) > 2 or len(base_rows) > 2:
            errors.append(f"{key}: ブロックが 2x2 を超える members={members}")
        for m in members:
            dx, dy = decode_ones(m)
            col, row = OBSERVED[m]
            exp_col = min(base_cols) + dx
            exp_row = min(base_rows) + dy
            if (col, row) != (exp_col, exp_row):
                errors.append(
                    f"{m}: 一の位デコード {dx,dy} と実測 {(col,row)} が不一致 "
                    f"(block起点 {(min(base_cols),min(base_rows))})"
                )
    return errors


if __name__ == "__main__":
    errs = verify_against_observed()
    if errs:
        print("自己無矛盾チェック: 不整合あり")
        for e in errs:
            print("  -", e)
    else:
        print("自己無矛盾チェック: OK（一の位デコードが実測と全一致）")
