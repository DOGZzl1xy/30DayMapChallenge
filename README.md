# 30 Day Map Challenge 2026 — Xuanyu

My maps for the [#30DayMapChallenge](https://30daymapchallenge.com/) 2026, made in Python, as part of the
[Weitzman MUSA collective gallery](https://weitzman-musa.github.io/30DayMapChallenge/).

## Repository layout

```
scripts/
  common.py              shared paths, cached downloads, credit line, save helper
  dayNN_<theme>/
    make_map.py          builds the map end to end (downloads its own data)
    README.md            what the map shows, data sources, method
    entry.md             text for the MUSA gallery entry
data/
  dayNN_<theme>/         small processed data (raw downloads go to raw/, git-ignored)
outputs/                 exported maps (PNG)
tools/
  mapday.py              scaffolds a new day and builds the gallery submission
```

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python scripts/day13_interactions/make_map.py
```

Each script fetches its own raw data into `data/dayNN_<theme>/raw/` on first run.

## Daily workflow

```bash
python tools/mapday.py new 13              # scaffold scripts/day13_interactions/
# ... make the map, fill in README.md and entry.md, commit and push this repo ...
python tools/mapday.py submit 13 --dry-run # preview thumbnail + gallery entry in cache/preview/
python tools/mapday.py submit 13           # commit them to the MUSA fork on branch day13-xuanyu
```

## Maps

| Day | Theme | Map |
|---:|---|---|
| 01 | Points | |
| 02 | Lines | |
| 03 | Polygons | |
| 04 | Clusters | |
| 05 | Senses: Sight | |
| 06 | Vintage | |
| 07 | 10 minute map | |
| 08 | Utopia | |
| 09 | Urban-rural | |
| 10 | Prompting only | |
| 11 | Senses: Sound | |
| 12 | Power | |
| 13 | Interactions | [Where would a message in a bottle end up?](scripts/day13_drifters/) |
| 14 | Borgesian map | [Philadelphia at 1:1](scripts/day14_borgesian/) |
| 15 | Inside out | |
| 16 | Collaborative map | |
| 17 | Light & dark | |
| 18 | NULL | |
| 19 | Senses: Smell | |
| 20 | Hexagons | |
| 21 | OpenStreetMap | |
| 22 | Projections | |
| 23 | Senses: Taste | |
| 24 | Network | |
| 25 | Is this a map? | |
| 26 | Water | |
| 27 | New tool | |
| 28 | Senses: Feeling | |
| 29 | Raster | |
| 30 | Pen & paper | |

Themes from the [MUSA 2026 categories](https://github.com/weitzman-musa/30DayMapChallenge/blob/main/CATEGORIES_2026.md).
