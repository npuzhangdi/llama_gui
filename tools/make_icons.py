# -*- coding: utf-8 -*-
"""生成程序与卸载程序的多尺寸 ICO 图标（仅构建期需要 Pillow，运行期不需要）。

Windows 10/11 会在不同位置索取不同尺寸的图标：
  任务栏 / 标题栏 16~32px，Alt-Tab / 任务管理器 32~64px，
  资源管理器大图标 / 跳转列表 96~256px，高 DPI 还会按 125%/150% 缩放。
因此这里输出 10 个原生尺寸，避免系统缩放导致图标空白或模糊。

<=128px 使用 32bpp BGRA DIB（兼容性最好，任务管理器与小图标路径稳定），
256px 使用 PNG 压缩（控制体积）。

用法：python tools/make_icons.py
产出：assets/app.ico、assets/uninstall.ico
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
S = 4                      # 超采样倍率，保证小尺寸图标边缘平滑
N = 256 * S
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


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


def _dib(image: Image.Image, size: int) -> bytes:
    """构造 32bpp BGRA + AND mask 的 ICO 位图（自下而上）。"""
    im = image.resize((size, size), Image.LANCZOS).convert("RGBA")
    im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    r, g, b, a = im.split()
    xor = Image.merge("RGBA", (b, g, r, a)).tobytes()
    and_row = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (and_row * size)   # 32bpp 已带 alpha，掩码全 0
    header = struct.pack("<IiiHHIIiiII",
                         40, size, size * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + xor + and_mask


def _png(image: Image.Image, size: int) -> bytes:
    buffer = io.BytesIO()
    image.resize((size, size), Image.LANCZOS).convert("RGBA").save(
        buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def write_ico(path: Path, image: Image.Image) -> None:
    payloads = [(s, _png(image, s) if s == 256 else _dib(image, s)) for s in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(payloads)))
    offset = 6 + 16 * len(payloads)
    for size, data in payloads:
        side = 0 if size == 256 else size
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _size, data in payloads:
        out += data
    path.write_bytes(bytes(out))


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, factory in (("app.ico", make_app_icon), ("uninstall.ico", make_uninstall_icon)):
        path = ASSETS / name
        write_ico(path, factory())
        print(f"{path.name}: {path.stat().st_size} bytes, {len(SIZES)} sizes {SIZES}")


if __name__ == "__main__":
    main()
