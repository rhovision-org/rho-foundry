"""Render the README motion study and its static storyboard."""

import argparse
from functools import cache
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
from subprocess import check_output

from PIL import Image, ImageColor, ImageDraw, ImageFont


WIDTH, HEIGHT, SCALE, FPS = 768, 432, 2, 12


def mix(start, end, amount):
    start, end = ImageColor.getrgb(start), ImageColor.getrgb(end)
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def ease(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


@cache
def font(family, size):
    path = check_output(["fc-match", "--format=%{file}", family], text=True)
    return ImageFont.truetype(path, round(size * SCALE))


class Canvas:
    def __init__(self, background):
        self.image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), background)
        self.pen = ImageDraw.Draw(self.image)

    @staticmethod
    def coords(xy):
        return tuple(round(value * SCALE) for value in xy)

    def txt(self, value, x, y, size, color, family, anchor="lt"):
        self.pen.text(self.coords((x, y)), value, fill=color, font=font(family, size), anchor=anchor)

    def rule(self, points, color, width=1):
        self.pen.line([self.coords(point) for point in points], fill=color,
                      width=max(1, round(width * SCALE)), joint="curve")

    def rect(self, rect, fill=None, outline=None, width=1, radius=0):
        if radius:
            self.pen.rounded_rectangle(self.coords(rect), round(radius * SCALE), fill=fill,
                                       outline=outline, width=max(1, round(width * SCALE)))
        else:
            self.pen.rectangle(self.coords(rect), fill=fill, outline=outline,
                               width=max(1, round(width * SCALE)))

    def disk(self, x, y, radius, fill=None, outline=None, width=1):
        self.pen.ellipse(self.coords((x-radius, y-radius, x+radius, y+radius)),
                         fill=fill, outline=outline, width=max(1, round(width * SCALE)))

    def arc(self, x, y, radius, start, end, color, width=1):
        self.pen.arc(self.coords((x-radius, y-radius, x+radius, y+radius)), start, end,
                     fill=color, width=max(1, round(width * SCALE)))

    def polygon(self, points, fill):
        self.pen.polygon([self.coords(p) for p in points], fill=fill)

    def arrow(self, start, end, color, width=2, head=8):
        self.rule([start, end], color, width)
        x, y = end
        angle = atan2(y - start[1], x - start[0])
        arms = [(x - head*cos(angle + offset), y - head*sin(angle + offset))
                for offset in (-0.55, 0.55)]
        self.polygon([end, *arms], color)

    def dashed(self, start, end, color, width=1, dash=5, gap=6):
        dx, dy = end[0] - start[0], end[1] - start[1]
        distance = hypot(dx, dy)
        for offset in range(0, round(distance), dash + gap):
            stop = min(offset + dash, distance)
            self.rule([(start[0]+dx*offset/distance, start[1]+dy*offset/distance),
                       (start[0]+dx*stop/distance, start[1]+dy*stop/distance)], color, width)

    def finish(self):
        return self.image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def export(frame, length, stills):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    panels = [frame(t) for t in stills]
    storyboard = Image.new("RGB", (WIDTH, len(panels) * HEIGHT + (len(panels)-1)*6), "#24242d")
    for index, panel in enumerate(panels):
        storyboard.paste(panel, (0, index * (HEIGHT + 6)))
    storyboard.save(args.out / "overview.png", optimize=True)

    # Keep a stable palette across frames so text and stationary areas do not shimmer.
    palette = storyboard.quantize(colors=112, method=Image.Quantize.MEDIANCUT)
    frames = [frame(i / FPS).quantize(palette=palette, dither=Image.Dither.NONE)
              for i in range(round(length * FPS))]
    frames[0].save(args.out / "overview.gif", save_all=True, append_images=frames[1:],
                   duration=round(1000/FPS), loop=0, disposal=1, optimize=True)


GROUND = "#252127"
GRID = "#53454a"
INK = "#fff1db"
SOFT = "#d7c5af"
AMBER = "#ffbc77"
CORAL = "#e58e74"
LILAC = "#e3c9ed"
HEAD = "Latin Modern Roman:style=10 Bold"
BODY = "Noto Sans"
NUM = "Noto Sans:style=Bold"

# Each possible (issued, held) pair in the recorded 32-seat, eight-hold fixture.
SEAT_STATES = [(issued, held) for held in range(9) for issued in range(33-held)]


def table_scene(c, t):
    c.txt("Held seats", 36, 135, 22, SOFT, BODY)
    for held in range(9):
        y = 335-19*held
        c.rule([(52, y), (462, y)], GRID)
    c.rule([(52, 169), (52, 345), (470, 345)], SOFT)
    for index, (issued, held) in enumerate(SEAT_STATES):
        x, y = 55+12.7*issued, 335-19*held
        displayed = ease((t-0.28-index*0.007)/0.33)
        c.disk(x, y, 2.4+1.0*displayed, mix(GRID, AMBER, displayed))
    c.txt("Issued seats", 457, 355, 22, SOFT, BODY, "rt")
    c.rule([(490, 145), (490, 377)], GRID)
    c.txt("32 seats", 518, 148, 34, INK, HEAD)
    c.txt("Hold limit 8", 518, 196, 25, SOFT, BODY)
    if t >= 2.33:
        c.txt("261", 517, 247, 65, AMBER, NUM)
        c.txt("stored states", 519, 326, 25, INK, BODY)


def symbolic_scene(c, t):
    c.txt("1,000,000 seats", 35, 133, 46, AMBER, NUM)
    c.txt("Hold limit 250,000", 35, 198, 27, SOFT, BODY)
    c.txt("Manager", 733, 155, 24, LILAC, BODY, "rt")
    c.txt("fill_quota", 733, 193, 29, INK, NUM, "rt")
    committed = t >= 5.92
    bar = (35, 254, 733, 292)
    c.rect(bar, fill=GRID, radius=4)
    if committed:
        c.rect((559, 254, 733, 292), fill=CORAL, radius=4)
        c.rule([(559, 251), (559, 297)], INK, 2)
    else:
        p = ease((t-4.2)/1.72)
        c.rule([(733, 249),(733-174*p, 249)], LILAC, 3)
        c.rule([(559, 252),(559, 294)], LILAC, 1)
    c.txt("750,000 free" if committed else "1,000,000 free", 37, 312, 29, INK, NUM)
    c.txt("250,000 held" if committed else "0 held", 733, 312, 29,
          AMBER if committed else SOFT, NUM, "rt")
    c.txt("0 issued", 38, 353, 22, SOFT, BODY)
    c.txt("Revision 1" if committed else "Revision 0", 733, 353, 22, LILAC, BODY, "rt")


def frame(t):
    c = Canvas(GROUND)
    enumeration = t < 3.9
    c.txt("Rho Foundry", 34, 22, 23, AMBER, HEAD)
    c.txt("Enumerate the states" if enumeration else "Compile the arithmetic", 33, 54, 50, INK, HEAD)
    c.rule([(34, 111), (734, 111)], GRID, 1.5)
    if enumeration:
        table_scene(c, t)
    else:
        symbolic_scene(c, t)
    c.rule([(34, 389), (734, 389)], GRID, 1.5)
    c.txt("Enumerated backend" if enumeration else "Symbolic backend", 35, 401, 21, SOFT, BODY)
    c.txt("One row per reachable state" if enumeration else "No state table · one update",
          733, 401, 21, INK, BODY, "rt")
    return c.finish()


if __name__ == "__main__":
    export(frame, 9.5, (3.0, 7.8))
