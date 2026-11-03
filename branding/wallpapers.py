#!/usr/bin/env python3
"""Generates MOX's own abstract wallpapers. Every image is original and drawn here."""
import math
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "overlay/usr/share/backgrounds/mox"
LIST = REPO / "overlay/usr/share/gnome-background-properties/mox.xml"
W, H = 2560, 1440
SETS = {
    "aurora": ("ribbons", ["#050b1e", "#0b3d5c", "#1fd1a5", "#8a5cf6"]),
    "ember": ("ribbons", ["#140608", "#6b1420", "#f0562e", "#ffc25a"]),
    "lagoon": ("dunes", ["#04202c", "#075a6e", "#17b3b8", "#a6f0dc"]),
    "orchid": ("glow", ["#14061f", "#5b1a8c", "#e0479e", "#ffb3a7"]),
    "dune": ("dunes", ["#2b1407", "#8c4417", "#e29245", "#ffe0ae"]),
    "midnight": ("glow", ["#03040c", "#10194a", "#2f4fd8", "#7fb4ff"]),
    "citrus": ("ribbons", ["#0c1c10", "#2f7a3a", "#c3d82e", "#fff27a"]),
    "glacier": ("dunes", ["#dfeefb", "#a7d0f0", "#5c9ad8", "#23508f"]),
    "blush": ("glow", ["#fff1ec", "#ffc7c2", "#f58fae", "#a56bd8"]),
    "forest": ("dunes", ["#04130e", "#0d3b2a", "#2b7a55", "#a3d977"]),
    "cobalt": ("ribbons", ["#020617", "#0a2a8a", "#1e7bff", "#7ee8ff"]),
    "copper": ("ribbons", ["#100a08", "#4a2a1a", "#b8703a", "#f3c79a"]),
    "mist": ("glow", ["#e9edf2", "#c4cfdc", "#8fa3bb", "#5c7290"]),
    "nebula": ("glow", ["#05030f", "#2a0f5e", "#b0268a", "#ff9c4a"]),
    "sage": ("dunes", ["#eef0e4", "#c4cfa9", "#83a07c", "#3f6b5c"]),
    "indigo": ("ribbons", ["#07041c", "#241a7a", "#6a3df0", "#f08bd6"]),
}


def rgb(code):
    return np.array([int(code[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255


def ramp(t, colors):
    stops = np.stack([rgb(c) for c in colors])
    t = np.clip(t, 0, 1) * (len(stops) - 1)
    low = np.minimum(t.astype(int), len(stops) - 2)
    part = (t - low)[..., None]
    part = part * part * (3 - 2 * part)
    return stops[low] * (1 - part) + stops[low + 1] * part


def waves(x, y, rng, count=5, scale=1.0):
    total = np.zeros_like(x)
    for index in range(count):
        angle = rng.uniform(0, math.tau)
        frequency = rng.uniform(1.2, 3.0) * (1 + index * 0.45) * scale
        total += np.sin((x * math.cos(angle) + y * math.sin(angle)) * frequency * math.tau + rng.uniform(0, math.tau)) / (1 + index)
    return total / 2.2


def draw(kind, colors, seed):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    x, y = x / H, y / H
    if kind == "ribbons":
        t = 0.10 + 0.22 * y
        for index in range(5):
            middle = 0.22 + index * 0.15 + rng.uniform(-0.03, 0.03)
            curve = middle + 0.13 * np.sin(x * rng.uniform(0.9, 1.7) + rng.uniform(0, math.tau)) + 0.05 * np.sin(x * rng.uniform(2.2, 3.4) + rng.uniform(0, math.tau))
            width = rng.uniform(0.06, 0.13) * (1 + 0.5 * np.sin(x * 1.3 + index))
            distance = (y - curve) / width
            t = t + (0.30 + index * 0.05) * np.exp(-distance ** 2) * (1 + 0.55 * np.tanh(distance))
    elif kind == "dunes":
        t = np.zeros_like(x)
        for layer in range(7):
            edge = 0.16 + layer * 0.13 + 0.07 * waves(x, y * 0.15, rng, 3, 0.6)
            t = np.where(y > edge, (layer + 1) / 7 + 0.05 * (y - edge), t)
        t = t * 0.7 + 0.3 * (0.5 + 0.5 * waves(x, y, rng, 3, 0.5))
        t = sum(np.roll(t, shift, axis=0) for shift in range(-5, 6)) / 11  # soft edges
    else:
        t = np.zeros_like(x)
        for _ in range(6):
            cx, cy, r = rng.uniform(0, W / H), rng.uniform(0, 1), rng.uniform(0.35, 0.8)
            t += np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (r * r)) * rng.uniform(0.35, 0.8)
        t = t / t.max() + 0.08 * waves(x, y, rng, 3, 0.6)
    image = ramp(t, colors)
    grain = rng.normal(0, 1.1 / 255, (H, W, 1)).astype(np.float32)  # stops banding on gradients
    return Image.fromarray((np.clip(image + grain, 0, 1) * 255).astype(np.uint8))


def main():
    entries = ["""  <wallpaper deleted="false">
    <name>MOX Living</name>
    <filename>/usr/share/backgrounds/mox/mox-living.xml</filename>
    <filename-dark>/usr/share/backgrounds/mox/mox-living.xml</filename-dark>
    <options>zoom</options>
    <pcolor>#1b1f4b</pcolor>
    <scolor>#c2477a</scolor>
  </wallpaper>"""]
    for seed, (name, (kind, colors)) in enumerate(SETS.items(), 11):
        draw(kind, colors, seed).save(OUT / f"{name}.jpg", quality=86, optimize=True)
        path = f"/usr/share/backgrounds/mox/{name}.jpg"
        entries.append(f"""  <wallpaper deleted="false">
    <name>{escape(name.title())}</name>
    <filename>{path}</filename>
    <filename-dark>{path}</filename-dark>
    <options>zoom</options>
    <pcolor>{colors[0]}</pcolor>
    <scolor>{colors[1]}</scolor>
  </wallpaper>""")
    LIST.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">\n<wallpapers>\n' + "\n".join(entries) + "\n</wallpapers>\n")


if __name__ == "__main__":
    main()
