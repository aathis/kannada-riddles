"""Pillow image provider (design doc §13).

Draws every screen deterministically in flat vector style.
Uses uharfbuzz + freetype for 100% accurate complex script shaping (Kannada).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config_loader import Settings
from ..models import Episode, Question

EMOJI_NATIVE_SIZE = 109  # NotoColorEmoji bitmap strikes require this size


def _hex_to_rgba(fill: str) -> tuple[int, int, int, int]:
    if fill.startswith("#"):
        fill = fill.lstrip("#")
        if len(fill) == 6:
            r = int(fill[0:2], 16)
            g = int(fill[2:4], 16)
            b = int(fill[4:6], 16)
            return (r, g, b, 255)
    return (255, 255, 255, 255)


def _render_shaped_text(font_path: str, font_size: int, text: str, fill: str) -> Image.Image:
    try:
        import freetype
        import uharfbuzz as hb
        import numpy as np

        color = _hex_to_rgba(fill)
        ft_face = freetype.Face(font_path)
        ft_face.set_char_size(font_size * 64)

        with open(font_path, "rb") as f:
            font_data = f.read()
        hb_face = hb.Face(font_data)
        hb_font = hb.Font(hb_face)
        hb_font.scale = (font_size * 64, font_size * 64)

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hb_font, buf)

        glyph_infos = buf.glyph_infos
        glyph_positions = buf.glyph_positions

        total_w = sum(pos.x_advance for pos in glyph_positions) // 64 + 40
        ascender = ft_face.size.ascender // 64
        descender = abs(ft_face.size.descender // 64)
        total_h = ascender + descender + 40

        img = Image.new("RGBA", (max(total_w, 1), max(total_h, 1)), (0, 0, 0, 0))

        pen_x = 20 * 64
        pen_y = (20 + ascender) * 64

        for info, pos in zip(glyph_infos, glyph_positions):
            ft_face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
            glyph = ft_face.glyph
            bitmap = glyph.bitmap

            x = (pen_x + pos.x_offset + glyph.bitmap_left * 64) // 64
            y = (pen_y + pos.y_offset - glyph.bitmap_top * 64) // 64

            if bitmap.width > 0 and bitmap.rows > 0:
                arr = np.array(bitmap.buffer, dtype=np.uint8).reshape(bitmap.rows, bitmap.width)
                glyph_img = Image.fromarray(arr)
                r, g, b, _ = color
                color_img = Image.new("RGBA", (bitmap.width, bitmap.rows), (r, g, b, 0))
                color_img.putalpha(glyph_img)
                img.paste(color_img, (x, y), color_img)

            pen_x += pos.x_advance
            pen_y += pos.y_advance

        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        return img
    except Exception:
        font = ImageFont.truetype(font_path, font_size)
        bbox = font.getbbox(text)
        w = max(1, bbox[2] - bbox[0] + 10)
        h = max(1, bbox[3] - bbox[1] + 10)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((-bbox[0], -bbox[1]), text, font=font, fill=fill)
        return img


def _render_wrapped_shaped_text(font_path: str, font_size: int, text: str, fill: str, max_w: int = 1550) -> Image.Image:
    """Renders text with automatic word wrapping and scaling to stay safely within max_w."""
    words = text.split(" ")
    lines = []
    curr = []
    for w in words:
        test_str = " ".join(curr + [w])
        img_test = _render_shaped_text(font_path, font_size, test_str, fill)
        if img_test.width > max_w and curr:
            lines.append(" ".join(curr))
            curr = [w]
        else:
            curr.append(w)
    if curr:
        lines.append(" ".join(curr))

    line_imgs = [_render_shaped_text(font_path, font_size, line, fill) for line in lines]
    total_h = sum(img.height for img in line_imgs) + (len(line_imgs) - 1) * 12
    total_w = max(img.width for img in line_imgs)

    combined = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    curr_y = 0
    for img in line_imgs:
        cx = (total_w - img.width) // 2
        combined.paste(img, (cx, curr_y), img)
        curr_y += img.height + 12

    if combined.width > max_w:
        scale = max_w / combined.width
        new_w = max_w
        new_h = int(combined.height * scale)
        combined = combined.resize((new_w, new_h), Image.LANCZOS)

    return combined


class PillowProvider:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.w = cfg.video.width
        self.h = cfg.video.height

    # ---------- font / drawing helpers ----------

    def _font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            for fallback in [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Supplemental/Arial.ttf"
            ]:
                if Path(fallback).exists():
                    try:
                        return ImageFont.truetype(fallback, size)
                    except Exception:
                        pass
            return ImageFont.load_default()

    def _emoji(self, char: str, target_h: int) -> Image.Image:
        """Render one emoji at its native bitmap size, then scale."""
        font = ImageFont.truetype(self.cfg.fonts.emoji, EMOJI_NATIVE_SIZE)
        canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((20, 20), char, font=font, embedded_color=True)
        box = canvas.getbbox()
        if box:
            canvas = canvas.crop(box)
        scale = target_h / max(1, canvas.height)
        return canvas.resize((max(1, int(canvas.width * scale)), target_h), Image.LANCZOS)

    def _gradient(self, top_hex: str, bottom_hex: str) -> Image.Image:
        top = Image.new("RGB", (1, 1), top_hex).getpixel((0, 0))
        bot = Image.new("RGB", (1, 1), bottom_hex).getpixel((0, 0))
        col = Image.new("RGB", (1, self.h))
        for y in range(self.h):
            t = y / (self.h - 1)
            col.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
        return col.resize((self.w, self.h))

    def _center_shaped_text(self, canvas: Image.Image, text: str,
                            font_path: str, font_size: int, y: int, fill: str, max_w: int = 1550) -> None:
        txt_img = _render_wrapped_shaped_text(font_path, font_size, text, fill, max_w=max_w)
        x = (self.w - txt_img.width) // 2
        canvas.paste(txt_img, (x, y), txt_img)

    def _brand_bar(self, img: Image.Image) -> None:
        pass

    def _render_clue_token(self, token: str, height: int) -> Image.Image:
        """Render a clue token which can be an emoji OR a text letter/word (e.g. 'Geo', 'B', 'y')."""
        c = self.cfg
        token_str = str(token).strip()
        is_text = token_str.isascii() and any(ch.isalnum() for ch in token_str)
        if is_text:
            font_size = int(height * 0.65)
            font = self._font(c.fonts.latin_bold, font_size)
            try:
                tw = int(font.getlength(token_str)) + 24
            except Exception:
                bbox = font.getbbox(token_str)
                tw = max(1, bbox[2] - bbox[0] + 24)

            ascent, descent = font.getmetrics() if hasattr(font, "getmetrics") else (int(font_size * 0.8), int(font_size * 0.2))
            line_height = ascent + descent
            baseline_y = (height - line_height) // 2 + ascent

            canvas = Image.new("RGBA", (tw, height), (0, 0, 0, 0))
            d = ImageDraw.Draw(canvas)
            d.text((12, baseline_y), token_str, font=font, anchor="ls", fill=(255, 255, 255, 255))
            return canvas
        else:
            return self._emoji(token_str, height)

    def _paste_emoji_row(self, img: Image.Image, emojis: list[str],
                         emoji_h: int = 300, y: int = 450, max_w: int = 1550) -> None:
        """Emoji / Text token + plus-sign row, horizontally centered with auto-scaling."""
        c = self.cfg
        count = len(emojis)
        if count == 0:
            return

        target_h = emoji_h
        # Auto-adjust emoji height if there are 3 or more emojis
        if count >= 3 and target_h >= 240:
            emoji_h = int(target_h * 0.75)  # Scale down height for 3+ emojis

        plus_font = self._font(c.fonts.latin_bold, int(emoji_h * 0.45))
        rendered = [self._render_clue_token(e, emoji_h) for e in emojis]
        tmp = ImageDraw.Draw(img)
        plus_box = tmp.textbbox((0, 0), "+", font=plus_font)
        plus_w = plus_box[2] - plus_box[0]
        gap = 40 if count >= 3 else 60

        total = sum(r.width for r in rendered) + (count - 1) * (plus_w + 2 * gap)

        # If total exceeds max_w, scale rendered emojis proportionally
        if total > max_w:
            scale_factor = max_w / total
            emoji_h = int(emoji_h * scale_factor)
            plus_font = self._font(c.fonts.latin_bold, int(emoji_h * 0.45))
            rendered = [self._render_clue_token(e, emoji_h) for e in emojis]
            plus_box = tmp.textbbox((0, 0), "+", font=plus_font)
            plus_w = plus_box[2] - plus_box[0]
            gap = max(15, int(gap * scale_factor))
            total = sum(r.width for r in rendered) + (count - 1) * (plus_w + 2 * gap)

        x = (self.w - total) // 2
        y_offset = (target_h - emoji_h) // 2 if target_h > emoji_h else 0
        actual_y = y + y_offset

        for i, r in enumerate(rendered):
            img.paste(r, (x, actual_y), r)
            x += r.width
            if i < count - 1:
                x += gap
                tmp.text((x, actual_y + emoji_h // 2 - (plus_box[3] - plus_box[1]) // 2 - plus_box[1]),
                         "+", font=plus_font, fill=c.colors.accent)
                x += plus_w + gap

    # ---------- screens ----------

    def intro_card(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        self._brand_bar(img)
        title_str = ep.title_en or ep.title_kn or "Guess the Word!"
        self._center_shaped_text(img, title_str, c.fonts.latin_bold, 105, 340, c.colors.text)
        self._center_shaped_text(img, "Fun Word Puzzle Quiz", c.fonts.latin_bold, 52, 540, c.colors.subtext)
        self._paste_emoji_row(img, ["🧩", "🤔"], emoji_h=100, y=700)
        img.save(out)
        return out

    def question_card(self, q: Question, total: int, out: Path,
                      countdown: int | None = None) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        d = ImageDraw.Draw(img)
        self._brand_bar(img)

        # 1. Badge at top center
        badge_str = f"QUESTION {q.id} / {total}"
        badge_img = _render_shaped_text(c.fonts.latin_bold, 44, badge_str, c.colors.bg_top)
        bw = badge_img.width
        bx = (self.w - bw) // 2
        d.rounded_rectangle([bx - 36, 120, bx + bw + 36, 215], radius=25, fill=c.colors.accent)
        img.paste(badge_img, (bx, 142), badge_img)

        # 2. Narration / Hint text description placed prominently below badge ONLY if provided
        if q.narration_kn and q.narration_kn.strip():
            self._center_shaped_text(img, q.narration_kn.strip(), c.fonts.latin_bold, 46, 250, c.colors.subtext, max_w=1550)

        # 3. Emojis row centered (shifted up ~10% to y=390)
        self._paste_emoji_row(img, q.clue_emojis, emoji_h=300, y=390)

        # 4. Prompt question text below emojis (customizable per question)
        prompt_str = (getattr(q, "prompt_text", None) or "CAN YOU GUESS THE WORD?").strip().upper()
        self._center_shaped_text(img, prompt_str, c.fonts.latin_bold, 68, 810, c.colors.text, max_w=1550)

        # 5. Countdown timer circle
        if countdown is not None:
            cx, cy, r = self.w - 160, self.h - 160, 95
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c.colors.timer_ring)
            d.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], fill=c.colors.bg_top)
            nf = self._font(c.fonts.latin_bold, 95)
            nb = d.textbbox((0, 0), str(countdown), font=nf)
            d.text((cx - (nb[2] - nb[0]) / 2 - nb[0], cy - (nb[3] - nb[1]) / 2 - nb[1]),
                   str(countdown), font=nf, fill=c.colors.text)
        img.save(out)
        return out

    def reveal_card(self, q: Question, total: int, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.reveal_top, c.colors.reveal_bottom)
        self._brand_bar(img)

        # Clean Answer reveal without clue emojis, perfectly centered
        self._center_shaped_text(img, "ANSWER", c.fonts.latin_bold, 65, 320, c.colors.subtext)
        ans_str = q.answer_en or q.answer_kn
        self._center_shaped_text(img, ans_str, c.fonts.latin_bold, 135, 460, c.colors.accent, max_w=1550)
        img.save(out)
        return out

    def outro_card(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        self._brand_bar(img)
        self._center_shaped_text(img, "THANK YOU FOR WATCHING!", c.fonts.latin_bold, 95, 280, c.colors.text)

        # Draw call-to-action row
        cta_img = _render_shaped_text(c.fonts.latin_bold, 50, "LIKE   |   SUBSCRIBE   |   COMMENT", c.colors.accent)
        thumbs = self._emoji("👍", 60)
        bell = self._emoji("🔔", 60)

        row_w = cta_img.width + thumbs.width + bell.width + 60
        rx = (self.w - row_w) // 2
        ry = 560

        img.paste(thumbs, (rx, ry), thumbs)
        img.paste(cta_img, (rx + thumbs.width + 20, ry), cta_img)
        img.paste(bell, (rx + thumbs.width + cta_img.width + 40, ry), bell)

        brand_name = c.branding.channel_name_en or "Riddle World"
        self._center_shaped_text(img, brand_name, c.fonts.latin_bold, 48, 750, c.colors.subtext)
        img.save(out)
        return out

    def thumbnail(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        full = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        self._brand_bar(full)
        title_str = ep.title_en or ep.title_kn or "Guess the Word!"
        self._center_shaped_text(full, title_str, c.fonts.latin_bold, 120, 210, c.colors.accent, max_w=1550)
        first = ep.questions[0]
        self._paste_emoji_row(full, first.clue_emojis, emoji_h=320, y=430)

        # Draw "= ❓" row: '=' as shaped text, '❓' as emoji image
        eq_img = _render_shaped_text(c.fonts.latin_bold, 110, "=", c.colors.text)
        q_emoji = self._emoji("❓", 110)
        total_w = eq_img.width + 20 + q_emoji.width
        start_x = (self.w - total_w) // 2
        full.paste(eq_img, (start_x, 830), eq_img)
        full.paste(q_emoji, (start_x + eq_img.width + 20, 830), q_emoji)

        full.resize((1280, 720), Image.LANCZOS).save(out)
        return out
