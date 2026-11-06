# -*- coding: utf-8 -*-
"""生成程序与卸载程序的多尺寸 ICO 图标（仅构建期需要 Pillow，运行期不需要）。

用法：python tools/make_icons.py
产出：assets/app.ico、assets/uninstall.ico
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
S = 4                      # 超采样倍率，保证小尺寸图标边缘平滑
N = 256 * S
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _gradient(c1, c2):
    small = Image.new("RGBA", (64, 64))
    for y in range(64):
        for x in range(64):
            t = x / 63 * 0.35 + y / 63 * 0.65
            small.putpixel((x, y), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)) + (255,))
    return small.resize((N, N), Image.BICUBIC)


def _canvas(c1, c2):
    grad = _gradient(c1, c2)
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle((6 * S, 6 * S, N - 6 * S, N - 6 * S),
                                           radius=56 * S, fill=255)
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # 左上角柔光
    glow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-40 * S, -70 * S, 170 * S, 130 * S), fill=(255, 255, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(28 * S))
    img = Image.alpha_composite(img, Image.composite(glow, Image.new("RGBA", (N, N), (0, 0, 0, 0)), mask))

    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10 * S, 10 * S, N - 10 * S, N - 10 * S),
                        radius=52 * S, outline=(255, 255, 255, 46), width=2 * S)
    return img, d


def _stroke(d, pts, width, color=(255, 255, 255, 255)):
    scaled = [(x * S, y * S) for x, y in pts]
    d.line(scaled, fill=color, width=width * S, joint="curve")
    r = width * S / 2
    for x, y in (scaled[0], scaled[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _sparkle(d, cx, cy, r, color=(255, 224, 158, 255)):
    k = r * 0.24
    pts = [(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
           (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)]
    d.polygon([(x * S, y * S) for x, y in pts], fill=color)


def make_app_icon() -> Image.Image:
    img, d = _canvas((124, 100, 248), (58, 116, 244))
    # 抽象 λ 字形：主斜笔 + 右支
    _stroke(d, [(70, 196), (126, 60)], 23)
    _stroke(d, [(110, 112), (188, 196)], 23)
    _sparkle(d, 196, 56, 20)
    return img.resize((256, 256), Image.LANCZOS)


def make_uninstall_icon() -> Image.Image:
    img, d = _canvas((255, 138, 108), (224, 69, 96))
    white = (255, 255, 255, 255)
    # 向下箭头
    _stroke(d, [(128, 66), (128, 156)], 20, white)
    _stroke(d, [(94, 124), (128, 160), (162, 124)], 20, white)
    # 托盘
    d.rounded_rectangle((64 * S, 180 * S, 192 * S, 194 * S), radius=7 * S, fill=white)
    return img.resize((256, 256), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, factory in (("app.ico", make_app_icon), ("uninstall.ico", make_uninstall_icon)):
        icon = factory()
        path = ASSETS / name
        icon.save(path, format="ICO", sizes=SIZES)
        print(f"{path.name}: {path.stat().st_size} bytes, {len(SIZES)} sizes")


if __name__ == "__main__":
    main()
