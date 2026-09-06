"""Trust draft preview — convert PDF pages to low-resolution, watermarked PNG images
so clients can review the draft without being able to download/print/copy.

Watermark: Iron Gate crest + "IGC — SAMPLE ONLY — NOT VALID UNTIL PAID" text
(diagonal, light gray).
"""
from __future__ import annotations
import os
from io import BytesIO
from typing import List, Optional

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

# Low-res DPI keeps screenshots useless while preserving readability
PREVIEW_DPI = 80          # 1.11x scale factor — clearly not print-quality
SCALE = PREVIEW_DPI / 72.0

WATERMARK_TEXT = "IGC — SAMPLE ONLY — NOT VALID UNTIL PAID"
WATERMARK_RGBA = (120, 120, 120, 60)  # very light gray, partial alpha

# Crest — the transparent Iron Gate logo, stamped as a faded crest behind text.
_CREST_PATH_CANDIDATES = (
    "/app/frontend/public/irongate-logo.png",
    "/app/frontend/build/irongate-logo.png",
)
_crest_cache: Optional[Image.Image] = None


def _load_crest() -> Optional[Image.Image]:
    global _crest_cache
    if _crest_cache is not None:
        return _crest_cache
    for p in _CREST_PATH_CANDIDATES:
        if os.path.exists(p):
            try:
                _crest_cache = Image.open(p).convert("RGBA")
                return _crest_cache
            except Exception:
                pass
    return None


def _load_font(size: int) -> ImageFont.ImageFont:
    # Try a few common fonts, fall back to default bitmap font
    for fp in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _apply_watermark(img: Image.Image) -> Image.Image:
    """Tile diagonal watermark across the image + stamp a faded Iron Gate crest."""
    base = img.convert("RGBA")
    W, H = base.size

    # ---------- (1) Faded crest, centered ----------
    crest = _load_crest()
    if crest is not None:
        target = max(1, int(min(W, H) * 0.45))
        c = crest.copy()
        c.thumbnail((target, target), Image.LANCZOS)
        # Fade to ~7% alpha so text remains readable on top
        r, g, b, a = c.split()
        a = a.point(lambda v: int(v * 0.07))
        c.putalpha(a)
        cx = (W - c.width) // 2
        cy = (H - c.height) // 2
        base.alpha_composite(c, (cx, cy))

    # ---------- (2) Diagonal SAMPLE ONLY text tiles ----------
    font_size = max(18, W // 26)
    font = _load_font(font_size)

    # Draw watermark on transparent overlay, rotate, composite
    tile_w = int(W * 1.4)
    tile_h = int(H * 1.4)
    overlay = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # measure text
    try:
        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = int(font_size * len(WATERMARK_TEXT) * 0.55), font_size

    step_y = max(text_h * 4, int(H / 4))
    step_x = max(text_w + 60, int(W / 2))
    y = -text_h
    row = 0
    while y < tile_h:
        x_offset = -text_w // 2 if (row % 2 == 0) else 0
        x = x_offset
        while x < tile_w:
            draw.text((x, y), WATERMARK_TEXT, font=font, fill=WATERMARK_RGBA)
            x += step_x
        y += step_y
        row += 1

    overlay = overlay.rotate(-28, resample=Image.BICUBIC, expand=False)
    # Center overlay on base
    ox = (tile_w - W) // 2
    oy = (tile_h - H) // 2
    crop = overlay.crop((ox, oy, ox + W, oy + H))
    out = Image.alpha_composite(base, crop)
    return out.convert("RGB")


def _downres(img: Image.Image) -> Image.Image:
    """Mild downsample to discourage screenshot harvesting."""
    W, H = img.size
    # target ~950px wide (readable on screen, noticeably low-res if printed)
    target_w = 950
    if W > target_w:
        new_h = int(H * target_w / W)
        img = img.resize((target_w, new_h), Image.LANCZOS)
    return img


def pdf_bytes_to_preview_pages(pdf_bytes: bytes, fmt: str = "JPEG") -> List[bytes]:
    """Return a list of image bytes (one per page) with watermark + low-res.
    Default format is JPEG (quality 72) for fast network transfer.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    out: List[bytes] = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            pil = page.render(scale=SCALE).to_pil()
            pil = _downres(pil)
            pil = _apply_watermark(pil)
            buf = BytesIO()
            if fmt.upper() == "JPEG":
                pil.convert("RGB").save(buf, format="JPEG", quality=72, optimize=True, progressive=True)
            elif fmt.upper() == "WEBP":
                pil.save(buf, format="WEBP", quality=75, method=4)
            else:
                pil.save(buf, format="PNG", optimize=True)
            out.append(buf.getvalue())
            page.close()
    finally:
        pdf.close()
    return out


def pdf_bytes_to_preview_page(pdf_bytes: bytes, page_index: int, fmt: str = "JPEG") -> bytes:
    """Render a single page (0-indexed). Much faster than rendering all pages."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if page_index < 0 or page_index >= len(pdf):
            raise IndexError("page out of range")
        page = pdf[page_index]
        try:
            pil = page.render(scale=SCALE).to_pil()
            pil = _downres(pil)
            pil = _apply_watermark(pil)
            buf = BytesIO()
            if fmt.upper() == "JPEG":
                pil.convert("RGB").save(buf, format="JPEG", quality=72, optimize=True, progressive=True)
            elif fmt.upper() == "WEBP":
                pil.save(buf, format="WEBP", quality=75, method=4)
            else:
                pil.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        finally:
            page.close()
    finally:
        pdf.close()


def page_count(pdf_bytes: bytes) -> int:
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return len(pdf)
    finally:
        pdf.close()
