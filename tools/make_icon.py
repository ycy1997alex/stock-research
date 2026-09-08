"""產生 `src/research/app.ico`（ToDo §1.1 第 22 條）。

**一次性工具，圖示產好就不必再跑** —— 留著是為了圖示要改的時候有來源，
而不是每次打包都重跑。

為什麼要多解析度：單一尺寸的 .ico 在某些地方會被縮放糊掉，或者乾脆退回
系統預設圖示。Windows 會從這七個尺寸裡挑最接近的那個。

為什麼不跟 market-barometer 用同一顆：兩支程式會同時出現在工作列與
「開始」搜尋結果裡。圖示一樣的話，使用者得靠文字分辨兩個視窗開哪個。

畫面本身刻意極簡 —— 16×16 之下任何細節都會糊掉，所以只有兩根 K 線：
一紅一綠，這是「個股」最短的視覺說法。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "research" / "app.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BG = (15, 17, 21, 255)        # 跟網頁那側的 --bg 同色
UP = (99, 198, 138, 255)      # 綠：收高
DOWN = (224, 107, 107, 255)   # 紅：收低
EDGE = (47, 53, 66, 255)

S = 256  # 先畫大的，再讓 Pillow 縮出其他尺寸


def _rounded_bg(d: ImageDraw.ImageDraw) -> None:
    d.rounded_rectangle([(6, 6), (S - 7, S - 7)], radius=46, fill=BG, outline=EDGE,
                        width=5)


def _candle(d: ImageDraw.ImageDraw, cx: int, top: int, bottom: int,
            body_top: int, body_bottom: int, colour, body_w: int) -> None:
    """一根 K 線：影線一條、實體一個矩形。"""
    wick = max(3, body_w // 5)
    d.rectangle([(cx - wick // 2, top), (cx - wick // 2 + wick, bottom)], fill=colour)
    d.rectangle([(cx - body_w // 2, body_top), (cx + body_w // 2, body_bottom)],
                fill=colour)


def build() -> Path:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _rounded_bg(d)

    body_w = 46
    # 左邊綠（實體偏上 = 收高），右邊紅（實體偏下 = 收低）
    _candle(d, cx=94, top=52, bottom=196, body_top=72, body_bottom=150,
            colour=UP, body_w=body_w)
    _candle(d, cx=166, top=68, bottom=212, body_top=118, body_bottom=190,
            colour=DOWN, body_w=body_w)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="ICO", sizes=SIZES)
    return OUT


if __name__ == "__main__":
    path = build()
    with Image.open(path) as check:
        got = sorted(check.info.get("sizes", []))
    print(f"wrote {path}")
    print(f"sizes = {got}")
    assert len(got) == len(SIZES), f"少了尺寸：{set(SIZES) - set(got)}"
    print("OK")
