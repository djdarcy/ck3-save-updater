"""face_crop_compare: crop the same screen region from several game screenshots and lay them side by side, labelled.

For judging faces by eye (djdarcy, 2026-11-03: side-by-side comparisons decide whether a faces change is an
improvement). The region is given as fractions of the screenshot (left, top, right, bottom), so screenshots taken at
different resolutions crop the same place; an image given with box "-" is used whole (an earlier crop).

Usage: python -I tests/one-offs/face_crop_compare.py <out.png> <scale> <label>=<image>@<l,t,r,b> [...]
  e.g. "old bytes=shots/005.webp@0.02,0.75,0.145,0.958" "earlier=beidh_four_states.png@-"
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def piece(spec: str, scale: float, height: int | None) -> tuple[str, Image.Image]:
    label, rest = spec.split("=", 1)
    path, box = rest.rsplit("@", 1)
    im = Image.open(path).convert("RGB")
    if box != "-":
        l, t, r, b = (float(x) for x in box.split(","))
        w, h = im.size
        im = im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    if height:
        im = im.resize((int(im.width * height / im.height), height), Image.LANCZOS)
    return label, im


def main():
    out, scale = Path(sys.argv[1]), float(sys.argv[2])
    first = piece(sys.argv[3], scale, None)
    pieces = [first] + [piece(s, scale, first[1].height) for s in sys.argv[4:]]
    pad, band = 12, 34
    width = sum(im.width for _, im in pieces) + pad * (len(pieces) + 1)
    height = first[1].height + band + pad * 2
    sheet = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    x = pad
    for label, im in pieces:
        sheet.paste(im, (x, pad))
        draw.text((x + 4, pad + im.height + 8), label, fill=(235, 235, 235))
        x += im.width + pad
    sheet.save(out)
    print(f"wrote {out} ({width}x{height})")


if __name__ == "__main__":
    main()
