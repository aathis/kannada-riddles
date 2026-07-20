"""Cross-platform font resolution.

The config lists Linux font paths. On other systems (macOS, Windows) those
don't exist, so: use the configured path if present, else search standard
font directories for the same filename, else download the Noto font once
into ./fonts/ and use that.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

SEARCH_DIRS = [
    FONTS_DIR,
    Path.home() / "Library/Fonts",            # macOS user
    Path("/Library/Fonts"),                    # macOS system
    Path("/System/Library/Fonts"),             # macOS builtin
    Path("/System/Library/Fonts/Supplemental"),
    Path("/usr/share/fonts"),                  # Linux
    Path("C:/Windows/Fonts"),                  # Windows
]

DOWNLOADS = {
    "NotoSansKannada-Regular.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSansKannada/hinted/ttf/NotoSansKannada-Regular.ttf",
    "NotoSansKannada-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSansKannada/hinted/ttf/NotoSansKannada-Bold.ttf",
    # Substitute for DejaVuSans-Bold when it isn't installed (e.g. macOS).
    "DejaVuSans-Bold.ttf":
        "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSans/hinted/ttf/NotoSans-Bold.ttf",
    "NotoColorEmoji.ttf":
        "https://raw.githubusercontent.com/googlefonts/noto-emoji/main/fonts/NotoColorEmoji.ttf",
}


def resolve_font(configured_path: str) -> str:
    path = Path(configured_path)
    if path.exists():
        return str(path)

    name = path.name
    for base in SEARCH_DIRS:
        if not base.is_dir():
            continue
        direct = base / name
        if direct.exists():
            return str(direct)
        hits = list(base.rglob(name)) if base != Path("/usr/share/fonts") else list(base.glob(f"*/*/{name}"))
        if hits:
            return str(hits[0])

    url = DOWNLOADS.get(name)
    if url is None:
        raise FileNotFoundError(
            f"Font {configured_path!r} not found and no download known for {name!r}. "
            f"Install it or fix the path in config/config.yaml."
        )
    FONTS_DIR.mkdir(exist_ok=True)
    target = FONTS_DIR / name
    print(f"Font {name} not found locally — downloading to {target} …")
    tmp = target.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(target)
    return str(target)
