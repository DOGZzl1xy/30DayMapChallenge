---
title: "Where would a message in a bottle end up?"
image: outputs/day13_drifters_02_world.png
thumb_image: outputs/day13_drifters_thumb.png
thumb_focus: 0.5,0.5
thumb_zoom: 1.0
extra: outputs/day13_drifters.gif
---
**Day 13 (Interactions)**: Wind and ocean currents interact to herd anything that floats into a few places. I let 46 years of real NOAA drifter tracks decide where a message in a bottle would go: 107,268 imaginary bottles, three in every 1° patch of open ocean, drift month by month for ten years. By then 56% are still at sea, almost all of them trapped in the five subtropical gyres (the ocean's garbage patches); 33% have reached coasts and shallow seas, and 11% polar waters.

![World map after ten years of drift: glowing orange clusters of bottles in the North and South Pacific, North and South Atlantic and Indian Ocean gyres, with cyan dots along coastlines where real drifters ran aground](MAP)

![Animation: bottles spread evenly over the oceans drain away from the equator and pile up in the five gyres over ten years](MAP2)

**How it works:**

- **Data**: 28,728 drifting buoys of NOAA's Global Drifter Program, 1979–2025, 48.9 million positions every six hours. I kept only drifters that had lost their drogue (sea anchor): they ride the surface and the wind, much like floating debris.
- **Model**: 25.1 million pairs of positions 30 days apart give the odds of drifting from any 1° cell to any other, a Markov chain after Maximenko et al. (2012) and van Sebille et al. (2012). Bottles step through these odds month by month; cells with too few observations (coasts, shallow seas, sea ice) keep whatever drifts in.
- **Check**: the modelled peaks sit where the garbage patches are known to be. The North Pacific one lands between Hawaii and California, and real drifters that started 5,000–12,000 km away sent their last signals from right there.
- **Map**: each dot is one bottle, glowing brighter where they crowd together. Cyan dots mark where 6,853 real drifters ran aground.

**Data sources:**

- Lumpkin, R. & Centurioni, L. (2019). [NOAA Global Drifter Program quality-controlled 6-hour interpolated data from ocean surface drifting buoys](https://doi.org/10.25921/7ntx-z961) (May 2025 release, via [NOAA Open Data on AWS](https://noaa-oar-hourly-gdp-pds.s3.amazonaws.com/index.html)).
- Land: [Natural Earth](https://www.naturalearthdata.com/).

**Tools:** Python (xarray/zarr, numpy, scipy, cartopy, matplotlib).
