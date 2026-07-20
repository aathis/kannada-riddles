"""Pillow image provider (design doc §13).

Draws every screen deterministically in flat vector style.
Implements the provider interface so an AI image service (DALL-E,
Stable Diffusion, ...) can replace it later without touching the renderer.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config_loader import Settings
from ..models import Episode, Question

EMOJI_NATIVE_SIZE = 109  # NotoColorEmoji bitmap strikes require this size


class PillowProvider:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.w = cfg.video.width
        self.h = cfg.video.height

    # ---------- font / drawing helpers ----------

    def _font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(path, size)

    def _emoji(self, char: str, target_h: int) -> Image.Image:
        """Render one emoji at its native bitmap size, then scale."""
        font = ImageFont.truetype(self.cfg.fonts.emoji, EMOJI_NATIVE_SIZE)
        canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((20, 20), char, font=font, embedded_color=True)
        box = canvas.getbbox()
        if box:
            canvas = canvas.crop(box)
        scale = target_h / canvas.height
        return canvas.resize((max(1, int(canvas.width * scale)), target_h), Image.LANCZOS)

    def _gradient(self, top_hex: str, bottom_hex: str) -> Image.Image:
        top = Image.new("RGB", (1, 1), top_hex).getpixel((0, 0))
        bot = Image.new("RGB", (1, 1), bottom_hex).getpixel((0, 0))
        col = Image.new("RGB", (1, self.h))
        for y in range(self.h):
            t = y / (self.h - 1)
            col.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
        return col.resize((self.w, self.h))

    def _center_text(self, draw: ImageDraw.ImageDraw, text: str,
                     font: ImageFont.FreeTypeFont, y: int, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((self.w - (box[2] - box[0])) / 2 - box[0], y), text, font=font, fill=fill)

    def _brand_bar(self, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        c = self.cfg
        f = self._font(c.fonts.kannada_bold, 40)
        draw.text((60, 40), c.branding.channel_name_kn, font=f, fill=c.colors.accent)

    def _paste_emoji_row(self, img: Image.Image, emojis: list[str],
                         emoji_h: int, y: int) -> None:
        """Emoji + plus-sign row, horizontally centered."""
        c = self.cfg
        plus_font = self._font(c.fonts.latin_bold, int(emoji_h * 0.45))
        rendered = [self._emoji(e, emoji_h) for e in emojis]
        tmp = ImageDraw.Draw(img)
        plus_box = tmp.textbbox((0, 0), "+", font=plus_font)
        plus_w = plus_box[2] - plus_box[0]
        gap = 70
        total = sum(r.width for r in rendered) + (len(rendered) - 1) * (plus_w + 2 * gap)
        x = (self.w - total) // 2
        for i, r in enumerate(rendered):
            img.paste(r, (x, y), r)
            x += r.width
            if i < len(rendered) - 1:
                x += gap
                tmp.text((x, y + emoji_h // 2 - (plus_box[3] - plus_box[1]) // 2 - plus_box[1]),
                         "+", font=plus_font, fill=c.colors.accent)
                x += plus_w + gap

    # ---------- screens ----------

    def intro_card(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        d = ImageDraw.Draw(img)
        self._brand_bar(img, d)
        self._center_text(d, ep.title_kn, self._font(c.fonts.kannada_bold, 130), 340, c.colors.text)
        self._center_text(d, ep.title_en, self._font(c.fonts.latin_bold, 60), 560, c.colors.subtext)
        self._center_text(d, "🧩  ▶  🤔", self._font(c.fonts.latin_bold, 70), 720, c.colors.accent)
        img.save(out)
        return out

    def question_card(self, q: Question, total: int, out: Path,
                      countdown: int | None = None) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        d = ImageDraw.Draw(img)
        self._brand_bar(img, d)

        badge = f"ಪ್ರಶ್ನೆ {q.id} / {total}"
        bf = self._font(c.fonts.kannada_bold, 55)
        bb = d.textbbox((0, 0), badge, font=bf)
        bw = bb[2] - bb[0]
        bx = (self.w - bw) / 2
        d.rounded_rectangle([bx - 40, 130, bx + bw + 40, 240], radius=30, fill=c.colors.accent)
        d.text((bx, 155), badge, font=bf, fill=c.colors.bg_top)

        self._paste_emoji_row(img, q.clue_emojis, emoji_h=360, y=350)
        self._center_text(d, "ಈ ಪದ ಯಾವುದು?", self._font(c.fonts.kannada_bold, 80), 820, c.colors.text)

        if countdown is not None:
            cx, cy, r = self.w - 180, self.h - 180, 110
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c.colors.timer_ring)
            d.ellipse([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14], fill=c.colors.bg_top)
            nf = self._font(c.fonts.latin_bold, 110)
            nb = d.textbbox((0, 0), str(countdown), font=nf)
            d.text((cx - (nb[2] - nb[0]) / 2 - nb[0], cy - (nb[3] - nb[1]) / 2 - nb[1]),
                   str(countdown), font=nf, fill=c.colors.text)
        img.save(out)
        return out

    def reveal_card(self, q: Question, total: int, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.reveal_top, c.colors.reveal_bottom)
        d = ImageDraw.Draw(img)
        self._brand_bar(img, d)
        self._paste_emoji_row(img, q.clue_emojis, emoji_h=200, y=170)
        self._center_text(d, "ಉತ್ತರ", self._font(c.fonts.kannada_bold, 60), 430, c.colors.subtext)
        self._center_text(d, q.answer_kn, self._font(c.fonts.kannada_bold, 150), 530, c.colors.accent)
        self._center_text(d, q.answer_en, self._font(c.fonts.latin_bold, 65), 770, c.colors.text)
        img.save(out)
        return out

    def outro_card(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        img = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        d = ImageDraw.Draw(img)
        self._brand_bar(img, d)
        self._center_text(d, "ಧನ್ಯವಾದಗಳು!", self._font(c.fonts.kannada_bold, 130), 300, c.colors.text)
        self._center_text(d, "👍  ಲೈಕ್   |   🔔  ಸಬ್ಸ್ಕ್ರೈಬ್   |   💬  ಕಾಮೆಂಟ್",
                          self._font(c.fonts.kannada_bold, 65), 560, c.colors.accent)
        self._center_text(d, c.branding.channel_name_en, self._font(c.fonts.latin_bold, 50),
                          760, c.colors.subtext)
        img.save(out)
        return out

    def thumbnail(self, ep: Episode, out: Path) -> Path:
        c = self.cfg
        full = self._gradient(c.colors.bg_top, c.colors.bg_bottom)
        d = ImageDraw.Draw(full)
        self._brand_bar(full, d)
        self._center_text(d, ep.title_kn, self._font(c.fonts.kannada_bold, 150), 250, c.colors.accent)
        first = ep.questions[0]
        self._paste_emoji_row(full, first.clue_emojis, emoji_h=340, y=470)
        self._center_text(d, "= ❓", self._font(c.fonts.latin_bold, 120), 860, c.colors.text)
        full.resize((1280, 720), Image.LANCZOS).save(out)
        return out
