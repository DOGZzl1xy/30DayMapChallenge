"""Daily workflow helper for the 30 Day Map Challenge.

    python tools/mapday.py new 13                 # scaffold scripts/day13_interactions/
    python tools/mapday.py new 13 indego_flows    # ...or pick your own folder suffix
    python tools/mapday.py submit 13 --dry-run    # preview gallery entry + thumbnail in cache/preview/
    python tools/mapday.py submit 13              # write them into the MUSA fork on branch day13-xuanyu and commit

`submit` reads scripts/dayNN_*/entry.md (title, images, thumbnail crop, gallery text),
then writes these files into the fork of weitzman-musa/30DayMapChallenge:

    _maps_2026/NN-xuanyu.md
    assets/thumbnails/2026/NN-xuanyu.png        square 600x600 gallery thumbnail
    assets/thumbnails/2026/NN-xuanyu-map.png    web-sized `image`, shown via ](MAP) in the text
    assets/thumbnails/2026/NN-xuanyu-map2.png   optional `extra` images, ](MAP2), ](MAP3) ...

entry.md front matter keys: title, image, thumb_image (defaults to image), thumb_focus,
thumb_zoom, extra (comma-separated paths; GIFs are copied as they are).

Pushing the branch and opening the PR are left as separate, deliberate steps.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FORK = ROOT.parent / "musa-30DayMapChallenge"
YEAR = 2026
NAME = "xuanyu"  # used in gallery file names
CREATOR = "Xuanyu"
REPO_URL = "https://github.com/DOGZzl1xy/30DayMapChallenge"
THUMB_SIZE = 600
FULL_MAX = 2000

THEMES = {
    1: "Points", 2: "Lines", 3: "Polygons", 4: "Clusters", 5: "Senses: Sight",
    6: "Vintage", 7: "10 minute map", 8: "Utopia", 9: "Urban-rural", 10: "Prompting only",
    11: "Senses: Sound", 12: "Power", 13: "Interactions", 14: "Borgesian map", 15: "Inside out",
    16: "Collaborative map", 17: "Light & dark", 18: "NULL", 19: "Senses: Smell", 20: "Hexagons",
    21: "OpenStreetMap", 22: "Projections", 23: "Senses: Taste", 24: "Network",
    25: "Is this a map?", 26: "Water", 27: "New tool", 28: "Senses: Feeling", 29: "Raster",
    30: "Pen & paper",
}

# --------------------------------------------------------------------------- templates

MAKE_MAP = '''"""Day __DAY__ - __THEME__: TODO one-line idea.

Run from the repo root:
    .venv/Scripts/python scripts/__SLUG__/make_map.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402,F401
import matplotlib.pyplot as plt  # noqa: E402

from common import credit, data_dir, fetch, save_map  # noqa: E402,F401

DAY = __DAY__
THEME = "__THEME__"
SLUG = "__SLUG__"


def load_data():
    raw = data_dir(SLUG, raw=True)  # git-ignored download cache  # noqa: F841
    # path = fetch("https://...", raw / "source.zip")
    raise NotImplementedError


def main():
    data = load_data()  # noqa: F841
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_axis_off()
    # ... draw ...
    credit(ax, DAY, THEME, data_source="TODO")
    save_map(fig, SLUG)


if __name__ == "__main__":
    main()
'''

README = """# Day __DAY__ - __THEME__

**TODO map title**

![TODO alt text](../../outputs/__SLUG__.png)

TODO: what the map shows and why.

## Data

- TODO source name and link

## Method

- TODO

## Reproduce

```bash
.venv/Scripts/python scripts/__SLUG__/make_map.py
```
"""

ENTRY = """---
title: "TODO map title"
image: outputs/__SLUG__.png
thumb_focus: 0.5,0.5   # centre of the square thumbnail, as fractions of width,height
thumb_zoom: 1.0        # 1 = largest square that fits; 2 = zoom in 2x
# thumb_image: outputs/other.png   # crop the thumbnail from a different image
# extra: outputs/a.png, outputs/b.gif   # more images, used in the text as ](MAP2), ](MAP3)
---
**Day __DAY__ (__THEME__)**: TODO short description of the map.

![TODO alt text describing the map](MAP)

**Data sources:**

- TODO

**Tools:** Python (geopandas, matplotlib).
"""

# --------------------------------------------------------------------------- helpers


def die(msg: str) -> None:
    sys.exit(f"error: {msg}")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def fill(template: str, day: int, slug: str) -> str:
    return (
        template.replace("__DAY__", str(day))
        .replace("__THEME__", THEMES[day])
        .replace("__SLUG__", slug)
    )


def day_dir(day: int) -> Path:
    matches = sorted((ROOT / "scripts").glob(f"day{day:02d}_*"))
    if not matches:
        die(f"no scripts/day{day:02d}_* folder; run `new {day}` first")
    if len(matches) > 1:
        die(f"several folders for day {day}: {[m.name for m in matches]}")
    return matches[0]


def parse_entry(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        die(f"{path} needs a front matter block between --- lines")
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        quoted = re.match(r'^"((?:[^"\\]|\\.)*)"|^\'([^\']*)\'', value)
        if quoted:
            value = quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
            value = value.replace('\\"', '"')
        else:
            value = value.split(" #")[0].strip()
        meta[key.strip()] = value
    return meta, m.group(2).strip() + "\n"


def square_thumbnail(img: Image.Image, focus: tuple[float, float], zoom: float) -> Image.Image:
    w, h = img.size
    side = min(w, h) / max(zoom, 1.0)
    cx, cy = focus[0] * w, focus[1] * h
    left = min(max(cx - side / 2, 0), w - side)
    top = min(max(cy - side / 2, 0), h - side)
    box = (round(left), round(top), round(left + side), round(top + side))
    return img.crop(box).resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)


def git(*args: str, cwd: Path = FORK, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        die(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


# --------------------------------------------------------------------------- commands


def cmd_new(args: argparse.Namespace) -> None:
    day = args.day
    if day not in THEMES:
        die("day must be 1-30")
    existing = sorted((ROOT / "scripts").glob(f"day{day:02d}_*"))
    if existing:
        die(f"{existing[0].relative_to(ROOT)} already exists")
    slug = f"day{day:02d}_{slugify(args.name or THEMES[day])}"
    folder = ROOT / "scripts" / slug
    folder.mkdir(parents=True)
    for name, template in [("make_map.py", MAKE_MAP), ("README.md", README), ("entry.md", ENTRY)]:
        (folder / name).write_text(fill(template, day, slug), encoding="utf-8", newline="\n")
    print(f"created scripts/{slug}/ (make_map.py, README.md, entry.md)")


def cmd_submit(args: argparse.Namespace) -> None:
    day = args.day
    folder = day_dir(day)
    slug = folder.name
    meta, body = parse_entry(folder / "entry.md")

    title = meta.get("title", "")
    if not title or "TODO" in title or "TODO" in body:
        die(f"fill in the TODOs in {folder.relative_to(ROOT)}/entry.md first")
    images = [meta.get("image", f"outputs/{slug}.png")]
    images += [p.strip() for p in meta.get("extra", "").split(",") if p.strip()]
    image_paths = [ROOT / p for p in images]
    thumb_src = ROOT / meta.get("thumb_image", images[0])
    for path in image_paths + [thumb_src]:
        if not path.exists():
            die(f"image not found: {path.relative_to(ROOT)}")
    focus = tuple(float(v) for v in meta.get("thumb_focus", "0.5,0.5").split(","))
    zoom = float(meta.get("thumb_zoom", "1.0"))

    stem = f"{day:02d}-{NAME}"
    thumb_rel = f"assets/thumbnails/{YEAR}/{stem}.png"
    full_rels = []
    for k, path in enumerate(image_paths):
        ext = ".gif" if path.suffix.lower() == ".gif" else ".png"
        full_rels.append(f"assets/thumbnails/{YEAR}/{stem}-map{k + 1 if k else ''}{ext}")
    entry_rel = f"_maps_{YEAR}/{stem}.md"
    source = f"{REPO_URL}/tree/main/scripts/{slug}"

    def image_md(rel):
        return f"({{{{ '/{rel}' | relative_url }}}})"

    if "](MAP)" not in body:
        first, _, rest = body.partition("\n\n")
        body = f"{first}\n\n![{title}](MAP)\n\n{rest}".rstrip() + "\n"
    for k, rel in enumerate(full_rels):
        body = body.replace(f"](MAP{k + 1 if k else ''})", "]" + image_md(rel))
    if re.search(r"\]\(MAP\d*\)", body):
        die("entry.md references a (MAPn) image that is not listed in `extra`")

    entry = (
        "---\n"
        f"day: {day}\n"
        f"creator: {CREATOR}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"thumbnail: /{thumb_rel}\n"
        f"source: {source}\n"
        "---\n\n"
        f"{body}"
    )

    if args.dry_run:
        out = ROOT / "cache" / "preview" / slug
    else:
        if not (FORK / ".git").exists():
            die(f"fork not found at {FORK}")
        if git("status", "--porcelain"):
            die(f"{FORK.name} has uncommitted changes; commit or stash them first")
        branch = f"day{day:02d}-{NAME}"
        git("fetch", "upstream", "main", "--quiet")
        git("switch", "-C", branch, "upstream/main", "--quiet")
        out = FORK

    written = [entry_rel, thumb_rel, *full_rels]
    for rel in written:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
    thumb = Image.open(thumb_src)
    thumb = thumb.convert("RGBA") if thumb.mode not in ("RGB", "RGBA") else thumb
    square_thumbnail(thumb, focus, zoom).save(out / thumb_rel, optimize=True)
    for path, rel in zip(image_paths, full_rels):
        if rel.endswith(".gif"):
            shutil.copyfile(path, out / rel)
        else:
            full = Image.open(path)
            full = full.convert("RGBA") if full.mode not in ("RGB", "RGBA") else full
            full.thumbnail((FULL_MAX, FULL_MAX), Image.LANCZOS)
            full.save(out / rel, optimize=True)
        size_mb = (out / rel).stat().st_size / 1e6
        if size_mb > 10:
            print(f"warning: {rel} is {size_mb:.1f} MB; consider a lighter file")
    (out / entry_rel).write_text(entry, encoding="utf-8", newline="\n")

    if args.dry_run:
        print(f"preview written to {out}")
        for rel in written:
            print(f"  {rel}")
        return

    git("add", *written)
    git("commit", "-m", f"Day {day} - {CREATOR}: {title}", "--quiet")
    print(f"committed on {FORK.name}@{branch}: {', '.join(written)}")

    # The entry's Source link must open: make sure the day folder is on GitHub.
    git("fetch", "origin", "--quiet", cwd=ROOT, check=False)
    if not git("ls-tree", "-d", "origin/main", f"scripts/{slug}", cwd=ROOT, check=False):
        print(f"warning: scripts/{slug} is not on {REPO_URL} yet - push this repo before opening the PR")
    print(
        "next:\n"
        f"  git -C {FORK} push -u origin {branch}\n"
        f"  gh pr create --repo weitzman-musa/30DayMapChallenge --head DOGZzl1xy:{branch} "
        f"--title \"Day {day} - {CREATOR}\""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="scaffold scripts/dayNN_<name>/")
    p_new.add_argument("day", type=int)
    p_new.add_argument("name", nargs="?", help="folder suffix (default: the day's theme)")
    p_new.set_defaults(func=cmd_new)

    p_sub = sub.add_parser("submit", help="build gallery entry + thumbnail in the MUSA fork")
    p_sub.add_argument("day", type=int)
    p_sub.add_argument("--dry-run", action="store_true", help="write to cache/preview/ instead of the fork")
    p_sub.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
