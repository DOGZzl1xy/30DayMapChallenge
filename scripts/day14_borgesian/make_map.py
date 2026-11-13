"""Day 14 - Borgesian map: Philadelphia at 1:1, one A4 sheet at a time.

In Borges's one-paragraph story "On Exactitude in Science" (1946), cartographers draw a map
of the empire at the size of the empire. This script draws one sheet of that map for
Philadelphia: an A4 page at scale 1:1, centred on the letter N of the compass rose in the
City Hall courtyard (Centre Square). Printed at 100 % it is a map at its own size, and it
shows what the best aerial photograph of the city has to say at that scale: a few pixels.

Data
- U.S. Census Bureau 2024 Gazetteer: Philadelphia city land area -> number of sheets
- U.S. Census Bureau 2024 cartographic boundary (places, 1:500k): city outline, sheet grid
- City of Philadelphia 2025 aerial survey, 3-inch (7.62 cm) pixels, Cloud-Optimized GeoTIFF
  copy on source.coop of the PASDA tiles: native pixels for the sheet and fine zoom levels
- City of Philadelphia 2024 aerial survey via the PASDA map service: coarse zoom levels

Outputs
    outputs/day14_borgesian_a4.pdf        the printable sheet (A4, print at 100 %)
    outputs/day14_borgesian_a4.png        the same sheet, 300 dpi
    outputs/day14_borgesian_0[1-4]_*.png  4:5 carousel: sheet, zoom, numbers, method

Run from the repo root:
    .venv/Scripts/python scripts/day14_borgesian/make_map.py
"""

import io
import logging
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import Window, from_bounds  # noqa: E402

from common import AUTHOR, HASHTAG, OUTPUTS, data_dir, fetch, save_map  # noqa: E402

DAY = 14
THEME = "Borgesian map"
SLUG = "day14_borgesian"
RAW = data_dir(SLUG, raw=True)

# the letter N of the compass rose in the City Hall courtyard, EPSG:2272 (PA South, US ft)
SPOT = (2693508.92, 236146.72)
COG_2025 = ("https://data.source.coop/nlebovits/phl-aerial-imagery/2025/26928e233974n/26928E233974N.tif")
PASDA_2024 = ("https://services.pasda.psu.edu/server/rest/services/pasda/PhiladelphiaImagery2024/"
              "MapServer/export")
GAZETTEER = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
             "2024_Gaz_place_national.zip")
PLACES = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_42_place_500k.zip"
PHILADELPHIA = "4260000"  # Census place GEOID

A4 = (0.210, 0.297)  # m
PIXEL_FT = 0.25  # 3-inch ground sample distance
PIXEL_M = PIXEL_FT * 0.3048
FT_MM = 304.8
SHEET_MM = 0.1  # thickness of 80 g/m2 office paper
SHEET_GSM = 80
ISS_KM = 400  # roughly the International Space Station's orbit
EVEREST_KM = 8.849
EARTH_KM = 40075

PAPER, PAPER_DARK, INK, RED, FAINT = "#f3eee2", "#e4dccb", "#26231f", "#a8442a", "#8c857a"
SERIF = "Palatino Linotype"
plt.rcParams["font.family"] = ["Bahnschrift", "Segoe UI", "DejaVu Sans"]
plt.rcParams["pdf.fonttype"] = 42  # embed TrueType fonts in the PDF
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

TO_M = Transformer.from_crs(2272, 32129, always_xy=True)  # PA South (metres) for the sheet grid
TO_LL = Transformer.from_crs(2272, 4326, always_xy=True)


# =========================================================================== data


def land_area_m2() -> int:
    path = fetch(GAZETTEER, RAW / "2024_Gaz_place_national.zip")
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        for line in io.TextIOWrapper(f, encoding="latin-1"):
            cols = line.rstrip("\n").split("\t")
            if cols[1] == PHILADELPHIA:
                return int(cols[6])  # ALAND, square metres
    raise ValueError("Philadelphia not found in the Gazetteer")


def city_outline():
    path = fetch(PLACES, RAW / "cb_2024_42_place_500k.zip")
    places = gpd.read_file(f"zip://{path.as_posix()}")
    return places[places["GEOID"] == PHILADELPHIA].to_crs(32129)


def numbers(city) -> dict:
    area = land_area_m2()
    sheets = area / (A4[0] * A4[1])
    minx, _, _, maxy = city.total_bounds
    xm, ym = TO_M.transform(*SPOT)
    return dict(
        area_km2=area / 1e6,
        sheets=round(sheets),
        stack_km=sheets * SHEET_MM / 1e6,
        tonnes=sheets * A4[0] * A4[1] * SHEET_GSM / 1e6,
        years=sheets / (365.25 * 24 * 3600),
        laps=sheets * A4[1] / 1000 / EARTH_KM,
        pixels=(A4[0] / PIXEL_M) * (A4[1] / PIXEL_M),
        # sheets are counted in rows and columns from the north-west corner of the city
        row=int((maxy - ym) // A4[1]) + 1,
        col=int((xm - minx) // A4[0]) + 1,
    )


def read_pixels(x0, x1, y0, y1):
    """Native 2025 pixels covering a box (EPSG:2272 ft), with a one-pixel margin."""
    with rasterio.open(f"/vsicurl/{COG_2025}") as src:
        w = from_bounds(x0, y0, x1, y1, src.transform)
        c0, r0 = int(np.floor(w.col_off)) - 1, int(np.floor(w.row_off)) - 1
        win = Window(c0, r0, int(np.ceil(w.width)) + 3, int(np.ceil(w.height)) + 3)
        return src.read([1, 2, 3], window=win), src.window_transform(win)


def pasda_image(half_ft, size=1000):
    """A mosaic around SPOT from the 2024 map service (for the coarse zoom levels)."""
    cx, cy = SPOT
    query = urllib.parse.urlencode(dict(bbox=f"{cx - half_ft},{cy - half_ft},{cx + half_ft},{cy + half_ft}",
                                        bboxSR=2272, imageSR=2272, size=f"{size},{size}", format="jpg",
                                        f="image"))
    path = RAW / f"pasda2024_{int(half_ft)}ft.jpg"
    if not path.exists():
        path.write_bytes(urllib.request.urlopen(f"{PASDA_2024}?{query}", timeout=180).read())
    img = np.asarray(Image.open(path).convert("RGB")).copy()
    img[(img >= 248).all(axis=-1)] = [int(PAPER[i:i + 2], 16) for i in (1, 3, 5)]  # no-data -> paper
    return img


# =========================================================================== the A4 sheet


def draw_sheet(n, city):
    """An A4 page at true size; all positions below are in millimetres."""
    W, H = 210, 297
    fig = plt.figure(figsize=(W / 25.4, H / 25.4), facecolor=PAPER)
    page = fig.add_axes([0, 0, 1, 1])
    page.set_xlim(0, W)
    page.set_ylim(0, H)
    page.axis("off")

    # map area: one millimetre on paper is one millimetre on the ground
    L, R, B, T = 15, 195, 58, 252
    mw, mh = R - L, T - B
    cx, cy = SPOT
    gx0, gy0 = cx - mw / 2 / FT_MM, cy - mh / 2 / FT_MM
    gx1, gy1 = cx + mw / 2 / FT_MM, cy + mh / 2 / FT_MM
    pixels, tr = read_pixels(gx0, gx1, gy0, gy1)
    ax = fig.add_axes([L / W, B / H, mw / W, mh / H])
    ax.set_xlim(0, mw)
    ax.set_ylim(0, mh)
    ax.axis("off")
    for r in range(pixels.shape[1]):
        for c in range(pixels.shape[2]):
            px, py = tr * (c, r)  # top-left corner of the pixel
            ax.add_patch(Rectangle(((px - gx0) * FT_MM, (py - PIXEL_FT - gy0) * FT_MM), PIXEL_FT * FT_MM,
                                   PIXEL_FT * FT_MM, facecolor=pixels[:, r, c] / 255, edgecolor="none"))

    # neat line with a millimetre ruler
    page.add_patch(Rectangle((L, B), mw, mh, fill=False, lw=0.8, ec=INK))
    for k in range(mw + 1):
        t = 2.2 if k % 10 == 0 else 1.4 if k % 5 == 0 else 0.7
        page.plot([L + k] * 2, [T, T + t], color=INK, lw=0.25)
        page.plot([L + k] * 2, [B, B - t], color=INK, lw=0.25)
    for k in range(mh + 1):
        t = 2.2 if k % 10 == 0 else 1.4 if k % 5 == 0 else 0.7
        page.plot([L, L - t], [B + k] * 2, color=INK, lw=0.25)
        page.plot([R, R + t], [B + k] * 2, color=INK, lw=0.25)
    lon0, lat1 = TO_LL.transform(gx0, gy1)
    lon1, lat0 = TO_LL.transform(gx1, gy0)
    page.text(L, T + 3.5, f"{lat1:.7f}° N   {-lon0:.7f}° W", fontsize=5.5, color=FAINT, va="bottom")
    page.text(R, B - 3.5, f"{lat0:.7f}° N   {-lon1:.7f}° W", fontsize=5.5, color=FAINT, va="top", ha="right")

    # title block
    page.text(L, 285, "PHILADELPHIA", fontsize=25, color=INK, family=SERIF, va="top")
    page.text(L, 272.5, "Centre Square  ·  City Hall courtyard  ·  the N of the compass rose", fontsize=7.5,
              color=INK, va="top")
    page.text(R, 285, "SCALE 1 : 1", fontsize=14, color=RED, ha="right", va="top")
    page.text(R, 274, f"Sheet  R {n['row']:,}  ·  C {n['col']:,}", fontsize=7.5, color=INK, ha="right", va="top")
    page.text(R, 269.5, f"one of {n['sheets']:,}", fontsize=7.5, color=INK, ha="right", va="top")

    # scale bar: ten centimetres drawn are ten centimetres of ground
    for k in range(10):
        page.add_patch(Rectangle((L + k * 10, 44), 10, 2, facecolor=INK if k % 2 == 0 else PAPER, ec=INK, lw=0.4))
    for k, label in [(0, "0"), (50, "5"), (100, "10 centimetres")]:
        page.text(L + k, 48, label, fontsize=6, color=INK, ha="center")
    page.text(L, 40, "One centimetre on this sheet is one centimetre in Centre Square.", fontsize=6, color=FAINT,
              va="top")

    # legend
    page.add_patch(Rectangle((L, 25.5), 6, 6, facecolor=pixels[:, 2, 2] / 255, ec=INK, lw=0.4))
    page.text(L + 9, 30.2, "One pixel of the 2025 aerial survey: 7.62 × 7.62 cm of ground.", fontsize=6,
              color=INK, va="center")
    page.text(L + 9, 26.8, f"The best photograph of the city fits {n['pixels']:.1f} of them on an A4 sheet.",
              fontsize=6, color=INK, va="center")
    page.text(L, 20, "Generalisation: none.", fontsize=6, color=FAINT, va="center")

    # location diagram
    loc = fig.add_axes([126 / W, 15 / H, 24 / W, 30 / H])
    loc.axis("off")
    city.plot(ax=loc, facecolor="none", edgecolor=INK, lw=0.4)
    loc.plot(*TO_M.transform(*SPOT), "o", color=RED, ms=2.5)
    loc.set_aspect("equal")
    page.text(138, 47.5, "LOCATION", fontsize=5, color=INK, ha="center")

    # adjoining sheets
    ox, oy, sw, sh = 160, 16, 7, 9.9
    for i in range(3):
        for j in range(3):
            page.add_patch(Rectangle((ox + j * sw, oy + (2 - i) * sh), sw, sh, fill=(i == j == 1),
                                     facecolor=RED, ec=INK, lw=0.4))
    page.text(ox + 1.5 * sw, 47.5, "ADJOINING SHEETS", fontsize=5, color=INK, ha="center")
    page.text(ox + 1.5 * sw, 12.5, f"R {n['row'] - 1:,}–{n['row'] + 1:,}\nC {n['col'] - 1:,}–{n['col'] + 1:,}",
              fontsize=4.6, color=FAINT, ha="center", va="top", linespacing=1.4)

    page.text(L, 8, "Imagery: City of Philadelphia, 2025 aerial survey (via PASDA). Land area: U.S. Census Bureau, "
              "2024 Gazetteer.   After J. L. Borges, “On Exactitude in Science” (1946).", fontsize=4.6, color=FAINT)
    page.text(L, 4.5, f"Print at 100 % and this sheet is a map at its own size.   Map: {AUTHOR}  ·  {HASHTAG} "
              f"Day {DAY}", fontsize=4.6, color=FAINT)
    return fig


# =========================================================================== 4:5 carousel


SLIDE = (7.2, 9.0)  # inches, 2160 x 2700 at 300 dpi


def slide(kicker, page_no):
    fig = plt.figure(figsize=SLIDE, facecolor=PAPER)
    fig.text(0.07, 0.95, kicker.upper(), color=RED, fontsize=9, va="top")
    fig.text(0.07, 0.03, f"Map: {AUTHOR}  ·  Imagery: City of Philadelphia  ·  {HASHTAG} Day {DAY}: {THEME}",
             color=FAINT, fontsize=7)
    fig.text(0.93, 0.03, f"{page_no}/4", color=FAINT, fontsize=7, ha="right")
    return fig


def slide_sheet(sheet_png, n):
    fig = plt.figure(figsize=SLIDE, facecolor=PAPER_DARK)
    img = np.asarray(Image.open(sheet_png).convert("RGB"))
    h = 0.86
    w = h * SLIDE[1] / SLIDE[0] * img.shape[1] / img.shape[0]
    x0, y0 = (1 - w) / 2, 0.075
    shadow = fig.add_axes([x0 + 0.006, y0 - 0.005, w, h])
    shadow.set_facecolor("#cfc5b1")
    shadow.set_xticks([])
    shadow.set_yticks([])
    for s in shadow.spines.values():
        s.set_visible(False)
    ax = fig.add_axes([x0, y0, w, h])
    ax.imshow(img, interpolation="lanczos")
    ax.axis("off")
    fig.text(0.5, 0.965, f"One sheet of a 1:1 map of Philadelphia  ·  {n['sheets']:,} to go", color=INK,
             fontsize=10, ha="center", va="top")
    fig.text(0.5, 0.03, f"{HASHTAG} Day {DAY}: {THEME}  ·  Map: {AUTHOR}   1/4", color=FAINT, fontsize=7,
             ha="center")
    return fig


def slide_zoom(n):
    fig = slide("Zoom in ten times, five times", 2)
    fig.text(0.07, 0.915, "The map runs out of detail\nbefore it reaches the territory", color=INK, fontsize=21,
             family=SERIF, va="top", linespacing=1.1)
    cx, cy = SPOT
    levels = [(10000, "10 km", "the city"), (1000, "1 km", "Center City"), (100, "100 m", "City Hall"),
              (10, "10 m", "the compass rose"), (1, "1 m", "the letter N"),
              (0.36, "21 × 29.7 cm", f"one A4 sheet: {n['pixels']:.1f} pixels")]
    size, gap_x = 0.27, 0.025
    height = size * SLIDE[0] / SLIDE[1]
    for k, (width_m, label, note) in enumerate(levels):
        col, row = k % 3, k // 3
        x0 = 0.07 + col * (size + gap_x)
        y0 = 0.555 - row * 0.3
        ax = fig.add_axes([x0, y0, size, height])
        half = width_m / 2 / 0.3048
        if width_m >= 1000:
            ax.imshow(pasda_image(half), extent=[-half, half, -half, half])
        else:
            pix, tr = read_pixels(cx - half, cx + half, cy - half, cy + half)
            gx0, gy0 = tr * (0, 0)
            gx1, gy1 = tr * (pix.shape[2], pix.shape[1])
            ax.imshow(np.moveaxis(pix, 0, -1), extent=[gx0 - cx, gx1 - cx, gy1 - cy, gy0 - cy],
                      interpolation="nearest")
        ax.set_xlim(-half, half)
        ax.set_ylim(-half, half)
        if width_m > 1:
            nxt = half / 10 if width_m > 10 else 0.5 / 0.3048
            ax.add_patch(Rectangle((-nxt, -nxt), 2 * nxt, 2 * nxt, fill=False, ec=RED, lw=1.1))
        else:  # the A4 footprint
            a4w, a4h = A4[0] / 0.3048, A4[1] / 0.3048
            ax.add_patch(Rectangle((-a4w / 2, -a4h / 2), a4w, a4h, fill=False, ec=RED, lw=1.1))
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(INK)
            s.set_linewidth(0.6)
        fig.text(x0, y0 + height + 0.008, label, color=INK, fontsize=10.5)
        fig.text(x0, y0 - 0.01, note, color=FAINT, fontsize=8, va="top")
    fig.text(0.07, 0.2, "At one metre you can still read the N.\nAt the size of a sheet of paper, the best "
             f"photograph of the city\nhas {n['pixels']:.1f} pixels left to say anything with.", color=INK,
             fontsize=11.5, family=SERIF, va="top", linespacing=1.4)
    fig.text(0.07, 0.068, "Red boxes: the next view. Coarse views: 2024 survey; fine views: 2025 survey, "
             "native 7.62 cm pixels.", color=FAINT, fontsize=7.5)
    return fig


def slide_numbers(n):
    fig = slide("The full map", 3)
    fig.text(0.07, 0.915, "To map all of Philadelphia\nat 1:1 on A4 paper", color=INK, fontsize=21, family=SERIF,
             va="top", linespacing=1.1)
    fig.text(0.07, 0.79, f"{n['sheets']:,}", color=RED, fontsize=40, va="top")
    fig.text(0.07, 0.715, f"sheets, for {n['area_km2']:.1f} km² of land", color=INK, fontsize=12, va="top")

    # how tall the stack would be
    ax = fig.add_axes([0.07, 0.3, 0.86, 0.33])
    items = [("Mount Everest", EVEREST_KM, FAINT), ("International Space Station", ISS_KM, FAINT),
             ("the stack of sheets", n["stack_km"], RED)]
    for k, (label, km, colour) in enumerate(items):
        ax.barh(k, km, color=colour, height=0.5)
        ax.text(km + 8, k, f"{label}  ·  {km:,.0f} km" if km > 20 else f"{label}  ·  {km:.1f} km",
                va="center", color=INK, fontsize=9)
    ax.set_xlim(0, n["stack_km"] * 1.55)
    ax.set_ylim(-0.6, 2.6)
    ax.axis("off")
    fig.text(0.07, 0.645, f"Stacked at {SHEET_MM} mm a sheet, the map stands {n['stack_km']:,.0f} km tall:",
             color=INK, fontsize=10, va="top")

    stats = [(f"{n['tonnes']:,.0f} t", "of paper"), (f"{n['years']:,.0f} years", "to print, one\nsheet a second"),
             (f"{n['laps']:.0f}×", "around the Earth,\nend to end")]
    for k, (big, small) in enumerate(stats):
        x = 0.07 + k * 0.3
        fig.text(x, 0.27, big, color=INK, fontsize=22, va="top")
        fig.text(x, 0.205, small, color=FAINT, fontsize=9, va="top", linespacing=1.35)
    fig.text(0.07, 0.1, f"And each sheet would show about {n['pixels']:.0f} pixels of the best photograph "
             "the city has.", color=INK, fontsize=10)
    return fig


def slide_about(n):
    fig = slide("How this map was made", 4)
    fig.text(0.07, 0.915, "A map the size\nof the territory", color=INK, fontsize=21, family=SERIF, va="top",
             linespacing=1.1)
    fig.text(0.07, 0.79, "In Borges's one-paragraph story “On Exactitude in Science” (1946), an empire's\n"
             "cartographers draw a map as large as the empire itself. Later generations find it\n"
             "useless and leave it to the sun and the winters. This is one sheet of that map.",
             color=FAINT, fontsize=8.5, va="top", linespacing=1.5)
    steps = [
        ("Count the sheets", f"Philadelphia has {n['area_km2']:.1f} km² of land (U.S. Census Bureau, 2024 "
         f"Gazetteer).\nAt 21 × 29.7 cm per sheet: {n['sheets']:,} sheets."),
        ("Number them", "A grid of A4 sheets in Pennsylvania South metres, counted in rows and\n"
         f"columns from the city's north-west corner: this is row {n['row']:,}, column {n['col']:,}."),
        ("Choose the spot", "Centre Square, where Penn planned the city's middle: the letter N of the\n"
         "compass rose in the City Hall courtyard."),
        ("Draw it at 1:1", "Every pixel of the city's 2025 aerial survey (7.62 cm) drawn at its true size.\n"
         "Print the PDF at 100 % and it covers exactly the ground it shows."),
    ]
    for k, (head, body) in enumerate(steps):
        y = 0.65 - k * 0.125
        fig.text(0.07, y, f"{k + 1}", color=RED, fontsize=20, family=SERIF, va="top")
        fig.text(0.14, y - 0.003, head, color=INK, fontsize=11.5, va="top")
        fig.text(0.14, y - 0.035, body, color=FAINT, fontsize=8.5, va="top", linespacing=1.45)
    fig.text(0.07, 0.11, "Data: City of Philadelphia aerial surveys 2024 and 2025 (PASDA; 2025 as Cloud-Optimized\n"
             "GeoTIFFs on source.coop); U.S. Census Bureau Gazetteer and cartographic boundaries 2024.\n"
             "Code: github.com/DOGZzl1xy/30DayMapChallenge", color=FAINT, fontsize=7.5, va="top", linespacing=1.5)
    return fig


def main():
    city = city_outline()
    n = numbers(city)
    print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in n.items()})

    sheet = draw_sheet(n, city)
    pdf = OUTPUTS / f"{SLUG}_a4.pdf"
    sheet.savefig(pdf, facecolor=PAPER)
    print(f"saved {pdf.relative_to(OUTPUTS.parent)}")
    sheet_png = save_map(sheet, f"{SLUG}_a4", dpi=300, facecolor=PAPER, bbox_inches=None)
    plt.close(sheet)

    for k, (name, fig) in enumerate([("sheet", slide_sheet(sheet_png, n)), ("zoom", slide_zoom(n)),
                                     ("numbers", slide_numbers(n)), ("about", slide_about(n))], start=1):
        save_map(fig, f"{SLUG}_{k:02d}_{name}", dpi=300, facecolor=fig.get_facecolor(), bbox_inches=None)
        plt.close(fig)


if __name__ == "__main__":
    main()
