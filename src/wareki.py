"""和暦 -> 西暦 ISO 8601 変換。"""

from __future__ import annotations

import re

# 元号 -> (西暦開始年, 元年=1 に対応する西暦) 。N年 = base + N。
# 例: 令和N年 = 2018 + N （令和1年=2019）。仕様の「令和N年 = 2017 + N」は
#   令和8年=2025 を意味するが、実際の令和8年は2026年。captureDate 例も 2026-04-21。
#   したがって正しくは 令和N年 = 2018 + N（令和8年=2026）を採用する。
ERA_BASE = {
    "令和": 2018,  # 令和1年 = 2019
    "平成": 1988,  # 平成1年 = 1989
    "昭和": 1925,  # 昭和1年 = 1926
}

_WAREKI_RE = re.compile(
    r"(?P<era>令和|平成|昭和)\s*"
    r"(?P<year>元|\d+)\s*年\s*"
    r"(?P<month>\d+)\s*月\s*"
    r"(?P<day>\d+)\s*日"
)


def wareki_to_iso(text: str | None) -> str | None:
    """'令和8年4月21日' のような和暦文字列を '2026-04-21' に変換する。

    変換できない/空の場合は None を返す。
    """
    if not text:
        return None
    s = str(text).strip()
    # 全角数字を半角へ
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    m = _WAREKI_RE.search(s)
    if not m:
        return None
    era = m.group("era")
    year_raw = m.group("year")
    year_n = 1 if year_raw == "元" else int(year_raw)
    year = ERA_BASE[era] + year_n
    month = int(m.group("month"))
    day = int(m.group("day"))
    return f"{year:04d}-{month:02d}-{day:02d}"
