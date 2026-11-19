"""Overlay and contact-sheet drawing helpers (Pillow + scipy)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .views import Canvas


def outline(mask: np.ndarray, width: int = 2) -> np.ndarray:
    m = mask.astype(bool)
    return m & ~ndimage.binary_erosion(m, iterations=width)


def guides(img: Image.Image, canvas: Canvas, height: float = 1.0, step: float = 0.1, label: str | None = None) -> Image.Image:
    """Horizontal guides every `step` of character height plus the h=0 axis."""
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)
    n = canvas.resolution_px
    k = 0
    while k * step <= height + 1e-9:
        z = k * step
        _, r = canvas.to_pixel(0, z)
        strong = abs((z / height) * 10 - round((z / height) * 10)) < 1e-6 and round(z / height * 10) % 5 == 0
        d.line([(0, float(r)), (n, float(r))], fill=(0, 120, 255, 200 if strong else 110), width=2 if strong else 1)
        d.text((4, float(r) - 12), f"{z:.2f}", fill=(0, 80, 200, 255))
        k += 1
    c, _ = canvas.to_pixel(0, 0)
    d.line([(float(c), 0), (float(c), n)], fill=(0, 160, 80, 140), width=1)
    if label:
        d.rectangle([0, 0, 8 * len(label) + 10, 18], fill=(255, 255, 255, 220))
        d.text((5, 3), label, fill=(0, 0, 0, 255))
    return img


def mask_overlay(ref_rgba: np.ndarray, mask: np.ndarray, canvas: Canvas, label: str, height: float = 1.0) -> Image.Image:
    base = Image.new("RGBA", ref_rgba.shape[1::-1], (255, 255, 255, 255))
    base.alpha_composite(Image.fromarray(ref_rgba, "RGBA"))
    arr = np.array(base)
    arr[outline(mask)] = (230, 30, 30, 255)
    return guides(Image.fromarray(arr, "RGBA"), canvas, height, label=label)


def diff_overlay(ref: np.ndarray, render: np.ndarray, canvas: Canvas, label: str, ref_rgba: np.ndarray | None = None,
                 height: float = 1.0) -> Image.Image:
    """White=both, red=reference only (model MISSING), blue=model only (model EXCESS)."""
    ref = ref.astype(bool)
    render = render.astype(bool)
    h, w = ref.shape
    arr = np.full((h, w, 4), 255, dtype=np.uint8)
    if ref_rgba is not None:
        faded = (ref_rgba[..., :3].astype(float) * 0.25 + 255 * 0.75).astype(np.uint8)
        a = ref_rgba[..., 3:4].astype(float) / 255
        arr[..., :3] = (faded * a + 255 * (1 - a)).astype(np.uint8)
    arr[ref & render] = (205, 205, 205, 255)
    arr[ref & ~render] = (225, 40, 40, 255)
    arr[render & ~ref] = (40, 90, 230, 255)
    return guides(Image.fromarray(arr, "RGBA"), canvas, height, label=label)


def contact_sheet(images: list[Image.Image], labels: list[str], pad: int = 8) -> Image.Image:
    if not images:
        raise ValueError("no images")
    w = sum(im.width for im in images) + pad * (len(images) + 1)
    h = max(im.height for im in images) + 2 * pad + 20
    sheet = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    d = ImageDraw.Draw(sheet)
    x = pad
    for im, lab in zip(images, labels):
        sheet.alpha_composite(im.convert("RGBA"), (x, pad + 20))
        d.text((x + 4, pad), lab, fill=(0, 0, 0, 255))
        x += im.width + pad
    return sheet
