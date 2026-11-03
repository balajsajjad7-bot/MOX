#!/usr/bin/env python3
"""Generates MOX wallpapers, icons and boot art into overlay/."""
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
WALL = REPO / "overlay/usr/share/backgrounds/mox"
ICONS = REPO / "overlay/usr/share/icons/hicolor"
PLY = REPO / "overlay/usr/share/plymouth/themes/mox"
SHARE = REPO / "overlay/usr/share/mox"
PHASES = {
    "dawn": ("#0b0a10", "#6b4a5e"),
    "day": ("#0a0d14", "#3f5f86"),
    "dusk": ("#0b090e", "#7a4634"),
    "night": ("#050507", "#262a44"),
    "graphite": ("#0d0e10", "#3a3d44"),
    "frost": ("#dfe7ef", "#ffffff"),
    "paper": ("#efece6", "#fbfaf7"),
}
LIGHT = "/usr/share/fonts/opentype/inter/Inter-Light.otf"
THIN = "/usr/share/fonts/opentype/inter/Inter-ExtraLight.otf"
ITALIC = "/usr/share/fonts/opentype/inter/Inter-LightItalic.otf"
QUOTE = "\u201cGive him a mask, and he will tell you the truth.\u201d"
AUTHOR = "Oscar Wilde"
TAGLINE = "QUANTUM-RESISTANT ENCRYPTION"


def rgb(code):
    return np.array([int(code[i:i + 2], 16) for i in (1, 3, 5)], float)


def wallpaper(colors, seed, width=3840, height=2160):
    """A dark field with one quiet band of light along the horizon."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(float)
    x /= width
    y /= height
    base, glow = map(rgb, colors)
    arc = 1.12 + 0.20 * (x - 0.62) ** 2
    distance = np.abs(y - arc + 0.34)
    light = np.exp(-(distance / 0.20) ** 2) * (0.30 + 0.70 * np.exp(-((x - 0.64) / 0.42) ** 2))
    fall = np.clip((y - (arc - 0.34)) / 0.5, 0, 1)
    light = light * (1 - fall * 0.55)
    image = base + (glow - base)[None, None, :] * light[..., None]
    image += rng.normal(0, 1.1, (height, width, 1))
    return Image.fromarray(np.clip(image, 0, 255).astype("uint8"))


def spaced(text, font, tracking, fill):
    """Render text with wide letter spacing on a transparent image."""
    width = sum(font.getlength(c) + tracking for c in text) - tracking
    ascent, descent = font.getmetrics()
    image = Image.new("RGBA", (int(width) + 4, ascent + descent + 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = 2.0
    for char in text:
        draw.text((x, 2), char, font=font, fill=fill)
        x += font.getlength(char) + tracking
    return image


def chime(path, rate=48000):
    """A short original startup tone."""
    seconds = 2.2
    t = np.arange(int(rate * seconds)) / rate
    tone = np.zeros_like(t)
    for start, freq, level in ((0.0, 220.0, 0.5), (0.12, 329.63, 0.4), (0.26, 440.0, 0.34), (0.42, 659.25, 0.2)):
        s = np.clip(t - start, 0, None)
        tone += level * (t >= start) * np.sin(2 * np.pi * freq * s) * np.exp(-s * 2.4) * np.clip(s / 0.04, 0, 1)
    delay = int(0.18 * rate)
    wet = np.concatenate([np.zeros(delay), tone[:-delay]]) * 0.25
    stereo = np.stack([tone + wet, tone + np.roll(wet, 900)], axis=1)
    stereo = stereo / np.abs(stereo).max() * 0.6
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((stereo * 32767).astype("<i2").tobytes())


def svg(source, target, size):
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(target), str(source)], check=True)


def main():
    WALL.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    for seed, (name, colors) in enumerate(PHASES.items(), 7):
        wallpaper(colors, seed).save(WALL / f"{name}.jpg", quality=92)
    template = (REPO / "branding/icon.svg.in").read_text()
    glyphs = {
        "mox-control": ("#5ee7ff", "#7c3aed", '<path d="M76 172V88l52 56 52-56v84"/>'),
        "mox-ai": ("#ff9a52", "#c026d3", '<path d="M128 66l16 46 46 16-46 16-16 46-16-46-46-16 46-16z"/>'),
        "mox-modo": ("#14b8a6", "#2563eb", '<path d="M72 170V92l40 42 40-42 0 78"/><circle cx="182" cy="150" r="14"/>'),
        "mox-runner": ("#22c55e", "#0ea5e9", '<path d="M104 80l76 48-76 48z"/>'),
        "mox-install": ("#f59e0b", "#ef4444", '<path d="M128 72v84M92 124l36 36 36-36M82 186h92"/>'),
        "mox-thispc": ("#64748b", "#1e293b", '<rect x="72" y="84" width="112" height="72" rx="8"/><path d="M104 182h48M128 156v26"/>'),
        "mox-news": ("#ef4444", "#7f1d1d", '<path d="M72 80h112v96H72zM92 104h72M92 128h72M92 152h44"/>'),
        "mox-tv": ("#8b5cf6", "#312e81", '<rect x="68" y="84" width="120" height="84" rx="8"/><path d="M104 190h48"/>'),
        "mox-home": ("#10b981", "#065f46", '<path d="M70 128l58-50 58 50M86 118v62h84v-62"/>'),
        "mox-browser": ("#22d3ee", "#4338ca", '<circle cx="128" cy="128" r="62"/><path d="M66 128h124M128 66c-34 36-34 88 0 124M128 66c34 36 34 88 0 124"/>'),
        "mox-dialer": ("#34d399", "#0f766e", '<path d="M82 84c-8 8-8 22 0 36 14 26 34 46 60 58 14 7 26 6 34-2l-20-22-14 8c-14-6-28-20-34-34l8-14z"/>'),
        "mox-office": ("#60a5fa", "#1e3a8a", '<path d="M86 66h60l26 26v98H86zM146 66v26h26M104 122h48M104 146h48"/>'),
        "mox-player": ("#fb7185", "#7c3aed", '<path d="M104 84l74 44-74 44z"/>'),
        "mox-downloader": ("#38bdf8", "#0f172a", '<path d="M128 70v86M94 124l34 34 34-34M82 186h92"/>'),
        "mox-tasks": ("#a3e635", "#14532d", '<path d="M70 150l30-36 26 22 30-46 30 30"/>'),
        "mox-mail": ("#a78bfa", "#0e7490", '<path d="M66 88h124v84H66zM66 92l62 46 62-46"/><circle cx="182" cy="168" r="12"/>'),
        "mox-chat": ("#38bdf8", "#1d4ed8", '<path d="M70 84h116v72h-70l-26 26v-26H70z"/>'),
    }
    build = REPO / "branding/.build"
    build.mkdir(exist_ok=True)
    for name, (one, two, path) in glyphs.items():
        source = build / f"{name}.svg"
        source.write_text(template.replace("@A@", one).replace("@B@", two).replace("@P@", path))
        for size in (48, 128, 256):
            svg(source, ICONS / f"{size}x{size}/apps/{name}.png", size)
        scalable = ICONS / "scalable/apps" / f"{name}.svg"
        scalable.parent.mkdir(parents=True, exist_ok=True)
        scalable.write_text(source.read_text())
    chime(SHARE / "startup.wav")
    logo = REPO / "branding/mox.svg"
    for size in (48, 128, 256):
        svg(logo, ICONS / f"{size}x{size}/apps/mox.png", size)
    svg(logo, SHARE / "logo.png", 512)
    white = (255, 255, 255, 255)
    spaced("MOX", ImageFont.truetype(THIN, 64), 26, white).save(SHARE / "logo-login.png")
    spaced("MOX", ImageFont.truetype(THIN, 120), 52, white).save(PLY / "wordmark.png")
    spaced(TAGLINE, ImageFont.truetype(LIGHT, 17), 6, (255, 255, 255, 120)).save(PLY / "tagline.png")
    spaced(QUOTE, ImageFont.truetype(ITALIC, 20), 0.6, (255, 255, 255, 170)).save(PLY / "quote.png")
    spaced(AUTHOR.upper(), ImageFont.truetype(LIGHT, 13), 4, (255, 255, 255, 95)).save(PLY / "author.png")
    Image.new("RGBA", (2, 1), (255, 255, 255, 150)).save(PLY / "line.png")
    for leftover in ("logo.png", "glow.png"):
        (PLY / leftover).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
