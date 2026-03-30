#!/usr/bin/env python3
"""Generate a Bridge app icon as .icns"""
import struct, zlib, subprocess
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    import math

    def make_icon(size):
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = int(size * 0.06)
        r = size - pad * 2

        # Gradient-like background circle
        for i in range(r, 0, -1):
            t = i / r
            col = (
                int(30 + 40 * t),
                int(30 + 60 * t),
                int(80 + 80 * t),
                255
            )
            draw.ellipse([pad + (r - i) // 2, pad + (r - i) // 2,
                          pad + (r + i) // 2, pad + (r + i) // 2], fill=col)

        # Three nodes: Claude (top), Obsidian (bottom-left), NotebookLM (bottom-right)
        cx, cy = size // 2, size // 2
        nr = max(4, size // 14)
        margin = size * 0.28

        nodes = [
            (cx, cy - int(margin * 0.8), '#A855F7'),    # Claude — purple, top
            (cx - int(margin * 0.85), cy + int(margin * 0.5), '#6366F1'),  # Obsidian — indigo, bottom-left
            (cx + int(margin * 0.85), cy + int(margin * 0.5), '#10B981'),  # NotebookLM — green, bottom-right
        ]

        lw = max(2, size // 60)
        for i, (x1, y1, _) in enumerate(nodes):
            for j, (x2, y2, _) in enumerate(nodes):
                if i < j:
                    draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 160), width=lw)

        for x, y, color in nodes:
            draw.ellipse([x - nr, y - nr, x + nr, y + nr], fill=color)

        return img

    # Build iconset
    iconset = Path('/tmp/Bridge.iconset')
    iconset.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        img = make_icon(s)
        img.save(iconset / f'icon_{s}x{s}.png')
        if s <= 512:
            img2 = make_icon(s * 2)
            img2.save(iconset / f'icon_{s}x{s}@2x.png')

    result = subprocess.run(
        ['iconutil', '-c', 'icns', str(iconset),
         '-o', '/Users/adityatotlani/Applications/Bridge.app/Contents/Resources/AppIcon.icns'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print('Icon created successfully')
    else:
        print(f'iconutil error: {result.stderr}')

except ImportError as e:
    print(f'Skipping icon: {e}')
