"""Shared helpers for the daily map scripts.

Each day's script lives in ``scripts/dayNN_<theme>/make_map.py`` and is run
from the repo root. It imports this module with::

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from common import ...
"""

from __future__ import annotations

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"

AUTHOR = "Xuanyu"
HASHTAG = "#30DayMapChallenge"


def data_dir(slug: str, raw: bool = False) -> Path:
    """Folder for a day's data. ``raw=True`` is git-ignored (re-downloadable)."""
    path = DATA / slug / "raw" if raw else DATA / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(url: str, dest: Path, force: bool = False, **kwargs) -> Path:
    """Download ``url`` to ``dest`` once; later runs reuse the cached file."""
    dest = Path(dest)
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120, **kwargs) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    return dest


def credit(ax, day: int, theme: str, data_source: str, **text_kwargs):
    """Small footer: author, data source and challenge day."""
    style = dict(fontsize=7, color="#555555", ha="left", va="top")
    style.update(text_kwargs)
    ax.text(
        0.0,
        -0.02,
        f"Map: {AUTHOR}  ·  Data: {data_source}  ·  {HASHTAG} Day {day}: {theme}",
        transform=ax.transAxes,
        **style,
    )


def save_map(fig, slug: str, dpi: int = 300, **kwargs) -> Path:
    """Save the final map to ``outputs/<slug>.png`` and return the path."""
    OUTPUTS.mkdir(exist_ok=True)
    out = OUTPUTS / f"{slug}.png"
    kwargs.setdefault("bbox_inches", "tight")
    fig.savefig(out, dpi=dpi, **kwargs)
    print(f"saved {out.relative_to(ROOT)}")
    return out
