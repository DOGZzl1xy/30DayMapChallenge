"""Day 13 - Interactions: where would a message in a bottle end up?

Wind and ocean currents interact to herd anything that floats into a handful of
convergence zones. This script lets 46 years of real NOAA drifter tracks decide
where bottles go:

1. download the 6-hourly Global Drifter Program positions (AWS Open Data, zarr)
2. keep drifters that lost their drogue (sea anchor): those ride the surface and
   the wind, much like floating debris
3. count how they move between 1-degree cells over 30 days -> transition matrix
4. release 3 bottles per open-ocean cell and step them through the matrix month by
   month for 10 years (Markov chain, after Maximenko et al. 2012 and van Sebille
   et al. 2012); the exact density is propagated alongside for the statistics

Outputs (4:5 social carousel + animation):
    outputs/day13_drifters_01_cover.png     glowing globe, title
    outputs/day13_drifters_02_world.png     the five gyres after ten years
    outputs/day13_drifters_03_timeline.png  start / 1 / 3 / 10 years
    outputs/day13_drifters_04_about.png     how it was made
    outputs/day13_drifters.mp4 / .gif       bottles drifting for ten years (--animate)

Run from the repo root:
    .venv/Scripts/python scripts/day13_drifters/make_map.py              # slides from cached model
    .venv/Scripts/python scripts/day13_drifters/make_map.py --rebuild    # recompute the model
    .venv/Scripts/python scripts/day13_drifters/make_map.py --animate    # also render the animation
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402
from scipy import ndimage  # noqa: E402

from common import AUTHOR, HASHTAG, OUTPUTS, data_dir, save_map  # noqa: E402

DAY = 13
THEME = "Interactions"
SLUG = "day13_drifters"
REPO = "github.com/DOGZzl1xy/30DayMapChallenge"

ZARR_URL = "https://noaa-oar-hourly-gdp-pds.s3.amazonaws.com/experimental/gdp6h_ragged_may25.zarr"
RAW = data_dir(SLUG, raw=True) / "gdp6h_may25_min.npz"
MODEL = data_dir(SLUG) / "bottles_model.npz"

LAG = 120  # 120 x 6 h = 30 days per step
MIN_PAIRS = 10  # observed departures a cell needs to count as open ocean
BOTTLES_PER_CELL = 3
MONTHS = 120
SNAP_MONTHS = (0, 12, 36, 120)
SEED = 13
NLAT, NLON = 180, 360

GYRES = {  # name: (lat_min, lat_max, lon_min, lon_max); lon in [-180, 180], may wrap
    "North Pacific": (15, 45, 120, -110),
    "North Atlantic": (15, 45, -80, -10),
    "South Pacific": (-45, -15, 150, -70),
    "South Atlantic": (-45, -15, -60, 20),
    "Indian Ocean": (-45, -15, 20, 120),
}

BG, LAND, OCEAN_DISC = "#040a12", "#101a26", "#06101c"
INK, MUTED, FAINT = "#eef3f8", "#93a4b8", "#5f7287"
ORANGE, SHORE, HALO, TRACK = "#ffb15e", "#a8ecf7", "#3b82c4", "#1f4d72"
GLOW_NORM = mcolors.LogNorm(0.3, 12, clip=True)
GLOW = mcolors.LinearSegmentedColormap.from_list(  # 1x (the even start) is plain blue; orange from ~2x
    "glow", [(0, "#2c6a8e"), (float(GLOW_NORM(1)), "#4f8fb0"), (float(GLOW_NORM(2)), "#e0784a"),
             (float(GLOW_NORM(5)), ORANGE), (1, "#fff4d6")])

PC = ccrs.PlateCarree()
WORLD = ccrs.EqualEarth(central_longitude=-160)
GLOBE = ccrs.Orthographic(central_longitude=-128, central_latitude=4)
SLIDE = (7.2, 9.0)  # inches; 4:5 at 300 dpi = 2160 x 2700 px
plt.rcParams["font.family"] = ["Inter", "Segoe UI", "DejaVu Sans"]
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


# =========================================================================== data


def download() -> None:
    """Fetch only the variables we need (~600 MB transfer) into the raw cache."""
    import xarray as xr

    print(f"downloading {ZARR_URL}")
    ds = xr.open_zarr(ZARR_URL, consolidated=True, decode_times=False)
    out = {v: ds[v].values for v in ["id", "rowsize", "typedeath", "end_lat", "end_lon"]}
    out["time"] = ds["time"].values.astype("f8")
    out["drogue_status"] = ds["drogue_status"].values.astype("i1")
    out["lat"] = ds["lat"].values.astype("f4")
    out["lon"] = ds["lon"].values.astype("f4")
    np.savez(RAW, **out)


def load_raw() -> dict:
    if not RAW.exists():
        download()
    return dict(np.load(RAW, allow_pickle=True))


def cell_index(lon, lat):
    row = np.clip(np.floor(lat + 90).astype(int), 0, NLAT - 1)
    col = np.clip(np.floor(lon + 180).astype(int), 0, NLON - 1)
    return row * NLON + col


def transition_matrix(d: dict):
    """Row-stochastic 30-day transition matrix between 1-degree cells."""
    lon, lat, drogue, rowsize, time = d["lon"], d["lat"], d["drogue_status"], d["rowsize"], d["time"]
    traj = np.repeat(np.arange(len(rowsize), dtype=np.int32), rowsize)
    # Positions sit on a 6-hourly grid, but ~0.5% of 30-day index pairs span a data gap:
    # keep only pairs exactly 30 days apart on the same drifter, starting undrogued.
    i = np.arange(len(lon) - LAG)
    keep = (traj[i] == traj[i + LAG]) & (drogue[i] == 0)
    keep &= np.isclose(time[i + LAG] - time[i], LAG * 6 * 3600)
    i = i[keep]
    a, b = cell_index(lon[i], lat[i]), cell_index(lon[i + LAG], lat[i + LAG])

    n = NLAT * NLON
    counts = sp.coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)).tocsr()
    departures = np.asarray(counts.sum(axis=1)).ravel()
    ocean = departures >= MIN_PAIRS
    # Cells without enough data (coasts, shallow seas, sea ice) keep whatever drifts in.
    T = sp.diags(np.where(ocean, 1 / np.maximum(departures, 1), 0)) @ counts
    T = (T + sp.diags(np.where(ocean, 0.0, 1.0))).tocsr()
    T.eliminate_zeros()
    T.sort_indices()
    return T, ocean, len(i)


def simulate_bottles(T, ocean, keep_months):
    """Step individual bottles through T; returns sub-cell offsets and cells per kept month."""
    rng = np.random.default_rng(SEED)
    n = T.shape[0]
    row_of = np.repeat(np.arange(n), np.diff(T.indptr))
    cum = np.cumsum(T.data)
    key = row_of + (cum - np.concatenate([[0.0], cum])[T.indptr[:-1]][row_of])  # sorted per-row CDFs

    cells = np.repeat(np.flatnonzero(ocean), BOTTLES_PER_CELL)
    offsets = rng.random((2, len(cells)))
    history = {0: cells.copy()}
    for month in range(1, max(keep_months) + 1):
        u = rng.random(len(cells)) * 0.999999
        cells = T.indices[np.searchsorted(key, cells + u, side="right")]
        if month in keep_months:
            history[month] = cells.copy()
    return offsets, history


def build_model() -> None:
    d = load_raw()
    T, ocean, n_pairs = transition_matrix(d)
    print(f"{n_pairs:,} undrogued 30-day position pairs")

    # exact density, for the numbers
    p = ocean / ocean.sum()
    density = {0: p.copy()}
    Tt = T.T.tocsr()
    for month in range(1, MONTHS + 1):
        p = Tt @ p
        if month in SNAP_MONTHS:
            density[month] = p.copy()

    offsets, bottles = simulate_bottles(T, ocean, set(SNAP_MONTHS))
    peaks = gyre_peaks(density[0], density[MONTHS], ocean)

    # background texture: 2,500 real undrogued-or-not drifter tracks, every 2 days
    rng = np.random.default_rng(SEED)
    rowsize = d["rowsize"]
    start = np.concatenate([[0], np.cumsum(rowsize)[:-1]])
    tr_lon, tr_lat = [], []
    for k in rng.choice(len(rowsize), 2500, replace=False):
        s = slice(start[k], start[k] + rowsize[k], 8)
        tr_lon += [d["lon"][s], [np.nan]]
        tr_lat += [d["lat"][s], [np.nan]]
    # for each gyre: of the drifters whose last fix lies within 1,000 km of the modelled
    # peak, the one that came from furthest away
    last = start + rowsize - 1
    first_lat, first_lon = d["lat"][start], d["lon"][start]
    last_lat, last_lon = d["lat"][last], d["lon"][last]
    km = great_circle_km(first_lat, first_lon, last_lat, last_lon)
    jr_lon, jr_lat, jr_names = [], [], []
    for name, g in peaks.items():
        near_peak = great_circle_km(last_lat, last_lon, g["lat"], g["lon"]) < 1000
        k = int(np.argmax(np.where(near_peak & (rowsize >= 4 * 365), km, -1)))
        s = slice(start[k], start[k] + rowsize[k], 4)
        jr_lon += [d["lon"][s], [np.nan]]
        jr_lat += [d["lat"][s], [np.nan]]
        jr_names.append(f"{name}: {km[k]:,.0f} km, {rowsize[k] / 4 / 365.25:.1f} yr")
    print("journeys:", jr_names)

    aground = d["typedeath"] == 1
    np.savez_compressed(
        MODEL,
        snap_months=np.array(SNAP_MONTHS),
        density=np.stack([density[m] for m in SNAP_MONTHS]).astype("f4"),
        bottles=np.stack([bottles[m] for m in SNAP_MONTHS]).astype("u2"),
        offsets=offsets.astype("f2"),
        ocean=ocean,
        aground_lon=d["end_lon"][aground].astype("f4"),
        aground_lat=d["end_lat"][aground].astype("f4"),
        track_lon=np.concatenate(tr_lon).astype("f2"),
        track_lat=np.concatenate(tr_lat).astype("f2"),
        journey_lon=np.concatenate(jr_lon).astype("f4"),
        journey_lat=np.concatenate(jr_lat).astype("f4"),
        n_drifters=len(rowsize),
        n_fixes=len(d["lon"]),
        n_pairs=n_pairs,
    )
    print(f"saved {MODEL.relative_to(MODEL.parents[2])}")


# =========================================================================== numbers


def in_box(lat, lon, box):
    la0, la1, lo0, lo1 = box
    in_lon = (lon >= lo0) & (lon < lo1) if lo0 < lo1 else (lon >= lo0) | (lon < lo1)
    return (lat >= la0) & (lat < la1) & in_lon


def great_circle_km(lat0, lon0, lat1, lon1):
    lat0, lon0, lat1, lon1 = (np.radians(np.asarray(v, float)) for v in (lat0, lon0, lat1, lon1))
    h = np.sin((lat1 - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin((lon1 - lon0) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(h))


def gyre_peaks(p0, p10, ocean):
    """Densest open-ocean cell of each gyre, as a multiple of the even start."""
    row, col = np.divmod(np.arange(NLAT * NLON), NLON)
    latc, lonc = row - 89.5, col - 179.5
    rel = p10 / p0.max()
    peaks = {}
    for name, box in GYRES.items():
        k = np.argmax(np.where(in_box(latc, lonc, box) & ocean, rel, 0))
        peaks[name] = dict(lat=latc[k], lon=lonc[k], peak=float(rel[k]))
    return peaks


def summarize(m):
    row, col = np.divmod(np.arange(NLAT * NLON), NLON)
    latc, lonc = row - 89.5, col - 179.5
    p10 = m["density"][-1]
    ocean = m["ocean"]
    lost = ~ocean
    in_any_gyre = np.zeros_like(ocean)
    for box in GYRES.values():
        in_any_gyre |= in_box(latc, lonc, box)
    s = {
        "adrift": float(p10[ocean].sum()),
        "adrift_in_gyres": float(p10[ocean & in_any_gyre].sum()),
        "coasts": float(p10[lost & (np.abs(latc) <= 60)].sum()),
        "polar": float(p10[lost & (np.abs(latc) > 60)].sum()),
        "gyres": gyre_peaks(m["density"][0], p10, ocean),
    }
    return s


# =========================================================================== drawing


def project(proj, lon, lat):
    p = proj.transform_points(PC, np.asarray(lon, float), np.asarray(lat, float))
    x, y = p[:, 0], p[:, 1]
    bad = ~np.isfinite(x) | ~np.isfinite(y)
    x[bad], y[bad] = np.nan, np.nan
    return x, y


def bottle_positions(m, cells):
    row, col = np.divmod(cells.astype(int), NLON)
    lon = col - 180 + m["offsets"][0].astype(float)
    lat = row - 90 + m["offsets"][1].astype(float)
    return lon, lat, m["ocean"][cells]


def bottle_glow_values(m, cells, adrift):
    """Local bottle density (1 = the even start) for each bottle, for colouring."""
    cnt = np.bincount(cells[adrift].astype(int), minlength=NLAT * NLON).reshape(NLAT, NLON)
    smooth = ndimage.gaussian_filter(cnt.astype(float), 1.2, mode="wrap") / BOTTLES_PER_CELL
    return smooth.ravel()[cells.astype(int)]


def draw_tracks(ax, proj, m, jump, lw=0.25, alpha=0.35):
    x, y = project(proj, m["track_lon"], m["track_lat"])
    x[np.abs(np.diff(x, prepend=x[0])) > jump] = np.nan  # break at the map seam
    ax.plot(x, y, lw=lw, color=TRACK, alpha=alpha, zorder=1, solid_capstyle="round")


def draw_bottles(ax, proj, m, cells, scale=1.0, every=1):
    lon, lat, adrift = bottle_positions(m, cells)
    value = bottle_glow_values(m, cells, adrift)
    x, y = project(proj, lon, lat)
    keep = adrift & np.isfinite(x)
    keep[np.arange(len(keep)) % every != 0] = False
    order = np.argsort(value[keep])
    x, y, colours = x[keep][order], y[keep][order], GLOW(GLOW_NORM(value[keep][order]))
    ax.scatter(x, y, s=14 * scale, c=colours, alpha=0.035, lw=0, zorder=3)  # halo
    ax.scatter(x, y, s=1.3 * scale, c=colours, alpha=0.9, lw=0, zorder=4)  # core


def draw_shore(ax, proj, m, scale=1.0):
    x, y = project(proj, m["aground_lon"], m["aground_lat"])
    ok = np.isfinite(x)
    ax.scatter(x[ok], y[ok], s=10 * scale, c=SHORE, alpha=0.06, lw=0, zorder=4)
    ax.scatter(x[ok], y[ok], s=1.1 * scale, c=SHORE, alpha=0.8, lw=0, zorder=4)


def world_axes(fig, rect, land_scale="50m"):
    ax = fig.add_axes(rect, projection=WORLD)
    ax.set_global()
    ax.set_facecolor(BG)
    ax.spines["geo"].set_visible(False)
    ax.add_feature(cfeature.LAND.with_scale(land_scale), facecolor=LAND, edgecolor="none", zorder=2)
    return ax


def globe_axes(fig, rect, pad=1.13):
    """Orthographic globe with a soft atmospheric halo drawn on a plain axes underneath."""
    under = fig.add_axes(rect)
    under.set_xlim(-pad, pad)
    under.set_ylim(-pad, pad)
    under.set_aspect("equal")
    under.axis("off")
    for k in range(40):
        under.add_patch(Circle((0, 0), 1 + 0.0035 * k, facecolor=HALO, alpha=0.03 * (1 - k / 40) ** 1.5,
                               edgecolor="none"))
    under.add_patch(Circle((0, 0), 1.0, facecolor=OCEAN_DISC, edgecolor="none"))
    ax = fig.add_axes(rect, projection=GLOBE)
    ax.patch.set_alpha(0)
    ax.set_global()
    ax.spines["geo"].set_visible(False)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=LAND, edgecolor="none", zorder=2)
    r = 6378137 * pad
    ax.set_xlim(-r, r)
    ax.set_ylim(-r, r)
    return ax


def halo_text(width=3):
    return [pe.withStroke(linewidth=width, foreground=BG)]


def slide(kicker=None):
    fig = plt.figure(figsize=SLIDE, facecolor=BG)
    if kicker:
        fig.text(0.07, 0.945, kicker.upper(), color=ORANGE, fontsize=9, fontweight="semibold", va="top")
    return fig


def footer(fig, page):
    fig.text(0.07, 0.03, f"Map: {AUTHOR}  ·  Data: NOAA Global Drifter Program  ·  {HASHTAG} Day {DAY}",
             color=FAINT, fontsize=7)
    fig.text(0.93, 0.03, f"{page}/4", color=FAINT, fontsize=7, ha="right")


def months_of(m, month):
    return m["bottles"][list(m["snap_months"]).index(month)]


# =========================================================================== slides


def slide_cover(m, s):
    fig = slide(f"{HASHTAG} · Day {DAY} · {THEME}")
    fig.text(0.07, 0.905, "Where would a\nmessage in a bottle\nend up?", color=INK, fontsize=33,
             fontweight="semibold", va="top", linespacing=1.08)
    ax = globe_axes(fig, [0.1075, 0.1185, 0.785, 0.785 * SLIDE[0] / SLIDE[1]])
    draw_tracks(ax, GLOBE, m, jump=3e6, lw=0.3)
    draw_bottles(ax, GLOBE, m, months_of(m, 120), scale=1.25)
    draw_shore(ax, GLOBE, m, scale=1.2)
    n = len(m["offsets"][0])
    fig.text(0.07, 0.085, f"{n:,} bottles, ten years at sea, moved by\n46 years of real ocean drifter tracks.",
             color=MUTED, fontsize=10.5, va="bottom", linespacing=1.4)
    fig.text(0.93, 0.085, "swipe →", color=ORANGE, fontsize=10.5, ha="right", va="bottom")
    footer(fig, 1)
    return fig


def slide_world(m, s):
    fig = slide("After ten years")
    fig.text(0.07, 0.905, "Half the bottles are still\nat sea, trapped in five gyres", color=INK, fontsize=24,
             fontweight="semibold", va="top", linespacing=1.12)
    fig.text(0.07, 0.79, "Winds push surface water toward the middle of each ocean basin, where it\n"
             "converges and sinks; floating things stay behind. These are the garbage patches.",
             color=MUTED, fontsize=9, va="top", linespacing=1.45)
    ax = world_axes(fig, [0.0, 0.325, 1.0, 0.40])
    draw_tracks(ax, WORLD, m, jump=5e6, lw=0.18, alpha=0.3)
    draw_bottles(ax, WORLD, m, months_of(m, 120), scale=0.55)
    draw_shore(ax, WORLD, m, scale=0.5)
    for name, g in s["gyres"].items():
        dy = 9 if g["lat"] > 0 else -9
        ax.text(g["lon"], g["lat"] + dy, f"{name}\n{g['peak']:.0f}×", transform=PC, ha="center",
                va="bottom" if dy > 0 else "top", color=INK, fontsize=7.5, fontweight="medium",
                linespacing=1.15, zorder=6, path_effects=halo_text(2.5))
    fig.text(0.07, 0.31, "×  peak density compared with the even start", color=FAINT, fontsize=7.5)

    stats = [(s["adrift"], "still adrift,\nmostly in the gyres", ORANGE),
             (s["coasts"], "reached coasts\nand shallow seas", SHORE),
             (s["polar"], "drifted into\npolar, icy seas", MUTED)]
    for k, (share, label, colour) in enumerate(stats):
        x = 0.07 + k * 0.30
        fig.text(x, 0.27, f"{share:.0%}", color=colour, fontsize=34, fontweight="semibold", va="top")
        fig.text(x, 0.185, label, color=MUTED, fontsize=9.5, va="top", linespacing=1.35)
    fig.text(0.07, 0.1, "●", color=SHORE, fontsize=8, va="center")
    fig.text(0.1, 0.1, f"Cyan dots: where {len(m['aground_lon']):,} real drifters actually ran aground.",
             color=FAINT, fontsize=8, va="center")
    footer(fig, 2)
    return fig


def slide_timeline(m, s):
    fig = slide("How they gather")
    n = len(m["offsets"][0])
    fig.text(0.07, 0.905, f"From everywhere\nto five places", color=INK, fontsize=24,
             fontweight="semibold", va="top", linespacing=1.12)
    panels = [(0, "Start", "one bottle in every patch of open ocean"),
              (12, "1 year", "the equator empties: currents push\nbottles north and south"),
              (36, "3 years", "the five gyres take shape"),
              (120, "10 years", "bottles still at sea pile up\nin the gyres")]
    w = 0.47
    h = w * SLIDE[0] / SLIDE[1] / 2.05  # Equal Earth is ~2.05:1
    for k, (month, title, caption) in enumerate(panels):
        col, row = k % 2, k // 2
        x0, y0 = 0.02 + col * (w + 0.02), 0.53 - row * 0.31
        ax = world_axes(fig, [x0, y0, w, h], land_scale="110m")
        draw_bottles(ax, WORLD, m, months_of(m, month), scale=0.3, every=3)
        fig.text(x0 + 0.05, y0 + h + 0.008, title, color=ORANGE, fontsize=11, fontweight="semibold")
        fig.text(x0 + 0.05, y0 - 0.005, caption, color=MUTED, fontsize=8, va="top", linespacing=1.35)
    fig.text(0.07, 0.085, f"Each dot is one bottle (every third of {n:,} shown).", color=FAINT, fontsize=8)
    footer(fig, 3)
    return fig


def slide_about(m, s):
    fig = slide("How this map was made")
    fig.text(0.07, 0.905, "Real drifters,\nimaginary bottles", color=INK, fontsize=24, fontweight="semibold",
             va="top", linespacing=1.12)
    steps = [
        ("46 years of real drifters",
         f"NOAA's Global Drifter Program has tracked {int(m['n_drifters']):,} buoys since 1979:\n"
         f"{int(m['n_fixes']) / 1e6:.1f} million positions, one every six hours."),
        ("Keep the ones that act like bottles",
         "Drifters that lost their sea anchor ride the surface and the wind,\nmuch like floating debris."),
        ("Learn how the sea moves things",
         f"{int(m['n_pairs']) / 1e6:.1f} million 30-day moves between 1° cells give the odds\n"
         "of drifting from any patch of ocean to any other."),
        ("Release the bottles",
         f"{BOTTLES_PER_CELL} bottles per open-ocean cell, stepped forward month by month\n"
         "for ten years (a Markov chain, after Maximenko et al. and van Sebille et al., 2012)."),
    ]
    for k, (head, body) in enumerate(steps):
        y = 0.78 - k * 0.093
        fig.text(0.07, y, f"{k + 1}", color=ORANGE, fontsize=20, fontweight="semibold", va="top")
        fig.text(0.14, y - 0.002, head, color=INK, fontsize=11.5, fontweight="semibold", va="top")
        fig.text(0.14, y - 0.031, body, color=MUTED, fontsize=8.5, va="top", linespacing=1.4)

    # real drifters whose journeys ended inside the gyres
    fig.text(0.07, 0.39, "Real drifters agree: five buoys whose last signals came from inside the gyres",
             color=MUTED, fontsize=8.5)
    ax = world_axes(fig, [0.0, 0.155, 1.0, 0.22], land_scale="110m")
    draw_tracks(ax, WORLD, m, jump=5e6, lw=0.12, alpha=0.25)
    x, y = project(WORLD, m["journey_lon"], m["journey_lat"])
    x[np.abs(np.diff(x, prepend=x[0])) > 5e6] = np.nan
    ax.plot(x, y, color=ORANGE, lw=0.9, alpha=0.95, zorder=3)
    breaks = np.flatnonzero(np.isnan(m["journey_lon"]))
    starts = np.concatenate([[0], breaks[:-1] + 1])
    ax.scatter(x[starts], y[starts], s=10, color=INK, zorder=4, lw=0)
    fig.text(0.07, 0.135, "●  start", color=INK, fontsize=7.5, va="top")
    fig.text(0.07, 0.11, "A model of average surface drift, not a forecast: real bottles also sink,\n"
             "break apart or get picked up.", color=FAINT, fontsize=8, va="top", linespacing=1.4)
    fig.text(0.07, 0.058, f"Code: {REPO}", color=FAINT, fontsize=7.5)
    footer(fig, 4)
    return fig


def render_slides(m) -> None:
    s = summarize(m)
    for k, (name, make) in enumerate([("cover", slide_cover), ("world", slide_world),
                                       ("timeline", slide_timeline), ("about", slide_about)], start=1):
        fig = make(m, s)
        save_map(fig, f"{SLUG}_{k:02d}_{name}", dpi=300, facecolor=BG, bbox_inches=None)
        plt.close(fig)
    # square, text-free globe for the gallery thumbnail
    fig = plt.figure(figsize=(6, 6), facecolor=BG)
    ax = globe_axes(fig, [0, 0, 1, 1], pad=1.06)
    draw_tracks(ax, GLOBE, m, jump=3e6, lw=0.3)
    draw_bottles(ax, GLOBE, m, months_of(m, 120), scale=1.0)
    draw_shore(ax, GLOBE, m, scale=1.0)
    save_map(fig, f"{SLUG}_thumb", dpi=200, facecolor=BG, bbox_inches=None)
    plt.close(fig)
    print({k: round(v, 3) for k, v in s.items() if k != "gyres"})
    for name, g in s["gyres"].items():
        print(f"  {name}: peak {g['peak']:.1f}x at {g['lat']}, {g['lon']}")


# =========================================================================== animation


def animate(m, fps=24, sub=2, hold=1.5) -> None:
    """Bottles drifting for ten years: MP4 for social media, lighter GIF for the gallery."""
    import imageio.v2 as imageio
    from PIL import Image

    T, ocean, _ = transition_matrix(load_raw())
    offsets, history = simulate_bottles(T, ocean, set(range(MONTHS + 1)))
    m = dict(m, offsets=offsets)

    # static background: rendered once, bottles are drawn on top in pixel space
    dpi = 150
    fig = slide(f"{HASHTAG} · Day {DAY} · {THEME}")
    fig.text(0.07, 0.905, "Where would a message\nin a bottle end up?", color=INK, fontsize=24,
             fontweight="semibold", va="top", linespacing=1.12)
    fig.text(0.07, 0.79, "Ten years of drift, from 46 years of real ocean drifter tracks",
             color=MUTED, fontsize=9.5, va="top")
    ax = world_axes(fig, [0.0, 0.3, 1.0, 0.44])
    draw_tracks(ax, WORLD, m, jump=5e6, lw=0.18, alpha=0.3)
    draw_shore(ax, WORLD, m, scale=0.5)
    footer(fig, 1)
    fig.texts[-1].set_visible(False)  # no page number on the video
    fig.set_dpi(dpi)
    fig.canvas.draw()
    background = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    height, width = background.shape[:2]
    to_pixels = ax.transData.transform

    positions = []
    for month in range(MONTHS + 1):
        lon, lat, adrift = bottle_positions(m, history[month])
        x, y = project(WORLD, lon, lat)
        px = to_pixels(np.column_stack([np.nan_to_num(x), np.nan_to_num(y)]))
        positions.append((px, adrift, bottle_glow_values(m, history[month], adrift)))
    plt.close(fig)

    def frame(month, f):
        (p0, a0, v0), (p1, a1, v1) = positions[month], positions[min(month + 1, MONTHS)]
        jump = np.abs(p1[:, 0] - p0[:, 0]) > width / 4
        p = np.where(jump[:, None], p1 if f >= 0.5 else p0, p0 + (p1 - p0) * f)
        alive = a0 & a1 if f > 0 else a0
        value = v0 * (1 - f) + v1 * f
        out = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
        canvas = out.add_axes([0, 0, 1, 1])
        canvas.imshow(background, extent=[0, width, 0, height], interpolation="nearest")
        canvas.set_xlim(0, width)
        canvas.set_ylim(0, height)
        canvas.axis("off")
        order = np.argsort(value[alive])
        colours = GLOW(GLOW_NORM(value[alive][order]))
        canvas.scatter(p[alive][order, 0], p[alive][order, 1], s=7.7, c=colours, alpha=0.035, lw=0)
        canvas.scatter(p[alive][order, 0], p[alive][order, 1], s=0.7, c=colours, alpha=0.9, lw=0)
        t = (month + f) / 12
        canvas.text(0.07 * width, 0.255 * height, f"Year {t:.1f}", color=INK, fontsize=22,
                    fontweight="semibold", va="top", family="Inter")
        canvas.plot([0.07 * width, 0.93 * width], [0.2 * height] * 2, color="#1c2a3a", lw=3,
                    solid_capstyle="round")
        canvas.plot([0.07 * width, (0.07 + 0.86 * t / 10) * width], [0.2 * height] * 2, color=ORANGE, lw=3,
                    solid_capstyle="round")
        share = a0.mean() if f == 0 else alive.mean()
        canvas.text(0.93 * width, 0.255 * height, f"{share:.0%} still adrift", color=MUTED, fontsize=11,
                    ha="right", va="top")
        out.canvas.draw()
        img = np.asarray(out.canvas.buffer_rgba())[..., :3].copy()
        plt.close(out)
        return img

    def to_gif(img):
        small = Image.fromarray(img).resize((width * 2 // 3, height * 2 // 3), Image.LANCZOS)
        return small.quantize(colors=96, method=Image.Quantize.FASTOCTREE)

    mp4 = OUTPUTS / f"{SLUG}.mp4"
    gif_frames = []
    steps = [(month, k / sub) for month in range(MONTHS) for k in range(sub)] + [(MONTHS, 0.0)]
    with imageio.get_writer(mp4, fps=fps, codec="libx264", quality=None, macro_block_size=2,
                            ffmpeg_params=["-crf", "26", "-preset", "slow"]) as writer:
        for n, (month, f) in enumerate(steps):
            img = frame(month, f)
            writer.append_data(img)
            if n % (sub * 2) == 0 or n == len(steps) - 1:  # GIF: one frame per two months
                gif_frames.append(to_gif(img))
        for _ in range(int(hold * fps)):
            writer.append_data(img)
    print(f"saved {mp4.relative_to(OUTPUTS.parent)} ({len(steps) + int(hold * fps)} frames)")

    gif = OUTPUTS / f"{SLUG}.gif"
    gif_frames[0].save(gif, save_all=True, append_images=gif_frames[1:] + [gif_frames[-1]] * 12,
                       duration=100, loop=0, optimize=True)
    print(f"saved {gif.relative_to(OUTPUTS.parent)} ({len(gif_frames)} frames)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="recompute the model from the raw data")
    parser.add_argument("--animate", action="store_true", help="also render the MP4/GIF animation")
    args = parser.parse_args()
    if args.rebuild or not MODEL.exists():
        build_model()
    m = dict(np.load(MODEL))
    render_slides(m)
    if args.animate:
        animate(m)


if __name__ == "__main__":
    main()
