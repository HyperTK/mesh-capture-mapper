"""PDF 捕獲記録（スキャン画像）からテキストを起こす OCR 補助。

位置づけ:
  横向きスキャン表の OCR は精度が出にくいため、これは「手起こしの下書き」
  を作るための補助ツール。出力は人が必ず目視で修正する前提。
  最終的な信頼できる入力は、確認済みの records CSV（手起こし）である。

依存（任意機能。未導入でも他モジュールは動く）:
  - poppler (PDF -> 画像) : `brew install poppler`
  - tesseract + jpn       : `brew install tesseract tesseract-lang`
  - pip: pdf2image, pytesseract, Pillow

使い方:
  python -m src.ocr_assist 捕獲記録.pdf -o data/input/ocr_draft.txt
  # 生成された生テキストを見ながら records CSV を手起こしする。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 認識しやすくするための設定。表は罫線が多いので PSM 6（単一ブロック）を既定に。
TESS_CONFIG = "--psm 6"
TESS_LANG = "jpn+eng"


def _require(modname: str):
    try:
        return __import__(modname)
    except ImportError as e:
        raise SystemExit(
            f"[ocr_assist] '{modname}' が必要です。`pip install .[ocr]` と "
            f"poppler/tesseract のインストールを確認してください。\n  詳細: {e}"
        )


def pdf_to_images(pdf_path: str | Path, dpi: int = 300) -> list:
    """PDF を 1 ページ 1 画像（PIL.Image）に変換する。"""
    _require("pdf2image")
    from pdf2image import convert_from_path  # type: ignore
    return convert_from_path(str(pdf_path), dpi=dpi)


def image_to_text(image, lang: str = TESS_LANG, config: str = TESS_CONFIG) -> str:
    _require("pytesseract")
    import pytesseract  # type: ignore
    return pytesseract.image_to_string(image, lang=lang, config=config)


def ocr_pdf(pdf_path: str | Path, dpi: int = 300) -> str:
    """PDF 全ページを OCR し、ページ区切り付きの生テキストを返す。"""
    out: list[str] = []
    for i, img in enumerate(pdf_to_images(pdf_path, dpi=dpi), start=1):
        out.append(f"===== page {i} =====")
        out.append(image_to_text(img))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="捕獲記録PDF -> OCR下書きテキスト（要・目視修正）")
    p.add_argument("pdf", help="捕獲記録 PDF（スキャン画像）")
    p.add_argument("-o", "--output", help="出力テキスト（省略時は標準出力）")
    p.add_argument("--dpi", type=int, default=300, help="ラスタライズ DPI（既定 300）")
    args = p.parse_args(argv)

    text = ocr_pdf(args.pdf, dpi=args.dpi)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"書き出し: {args.output}", file=sys.stderr)
        print("⚠ OCR結果は下書きです。records CSV は必ず目視で確認・修正してください。",
              file=sys.stderr)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
