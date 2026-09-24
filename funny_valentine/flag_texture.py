"""
A sharp redraw of Funny Valentine's flag (the 13-star Betsy Ross flag from the SFM pack's
flag.vtf, which is only 256x256). Same layout as that texture, so it drops onto the SFM flag's
UVs as-is: square, black border, 13 stripes with dark seams, union over the top 7 stripes,
13 upright stars in a ring.

    python flag_texture.py out.png [size]      (needs numpy)
"""
import math
import struct
import sys
import zlib

import numpy as np

# measured off the SFM texture (256 px square)
SRC = 256.0
BORDER = 4.0
UNION_X1, UNION_Y1 = 167.5, 135.5          # union spans from the border to here
RING_CX, RING_CY, RING_R = 84.5, 69.3, 54.5
STAR_R = 8.3                                # outer radius of each star (they all point up)
RED = (179, 8, 48)
WHITE = (240, 248, 240)
NAVY = (0, 36, 98)
SEAM = (96, 4, 26)
INK = (12, 6, 10)


def star_mask(xx, yy, cx, cy, r_out, angle):
    """Inside test for a 5-point star centred on (cx, cy), one point towards `angle` (radians, y down)."""
    r_in = r_out * 0.382
    verts = []
    for k in range(10):
        a = angle + k * math.pi / 5
        r = r_out if k % 2 == 0 else r_in
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    inside = np.zeros(xx.shape, bool)
    for (x0, y0), (x1, y1) in zip(verts, verts[1:] + verts[:1]):
        crosses = (y0 > yy) != (y1 > yy)
        xint = x0 + (yy - y0) * (x1 - x0) / ((y1 - y0) if y1 != y0 else 1e-9)
        inside ^= crosses & (xx < xint)
    return inside


def make_flag(size=2048, ss=2):
    n = size * ss
    s = n / SRC                               # source px -> supersampled px
    img = np.empty((n, n, 3), np.uint8)
    img[:] = INK
    y = (np.arange(n) + 0.5) / s              # row centre in source units
    top, bottom = BORDER, SRC - BORDER
    stripe_h = (bottom - top) / 13
    idx = np.clip(((y - top) // stripe_h).astype(int), 0, 12)
    rows = (y >= top) & (y < bottom)
    for i in range(13):
        band = rows & (idx == i)
        img[band, int(BORDER * s):int((SRC - BORDER) * s)] = RED if i % 2 == 0 else WHITE
    # dark seam along the bottom of each stripe
    seam = 1.2
    for i in range(1, 13):
        yb = top + i * stripe_h
        img[int((yb - seam) * s):int(yb * s), int(BORDER * s):int((SRC - BORDER) * s)] = SEAM
    # union with an ink outline
    ux0, uy0, ux1, uy1 = int(BORDER * s), int(BORDER * s), int(UNION_X1 * s), int(UNION_Y1 * s)
    img[uy0:uy1 + int(1.2 * s), ux0:ux1 + int(1.2 * s)] = INK
    img[uy0:uy1, ux0:ux1] = NAVY
    # stars
    for k in range(13):
        a = -math.pi / 2 + k * 2 * math.pi / 13
        cx, cy = RING_CX + RING_R * math.cos(a), RING_CY + RING_R * math.sin(a)
        x0, x1 = int((cx - STAR_R - 1) * s), int((cx + STAR_R + 1) * s)
        y0, y1 = int((cy - STAR_R - 1) * s), int((cy + STAR_R + 1) * s)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        m = star_mask((xx + 0.5) / s, (yy + 0.5) / s, cx, cy, STAR_R, -math.pi / 2)
        img[y0:y1, x0:x1][m] = WHITE
    # box-filter the supersampling away
    return img.reshape(size, ss, size, ss, 3).mean((1, 3)).round().astype(np.uint8)


def write_png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "fv_flag_color.png"
    write_png(out, make_flag(int(sys.argv[2]) if len(sys.argv) > 2 else 2048))
    print("wrote", out)
