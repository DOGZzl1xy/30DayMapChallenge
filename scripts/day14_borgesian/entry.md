---
title: "Philadelphia at 1:1"
image: outputs/day14_borgesian_a4.png
thumb_focus: 0.5,0.36   # title block and the top of the map
thumb_zoom: 1.0
extra: outputs/day14_borgesian_02_zoom.png, outputs/day14_borgesian_03_numbers.png
---
**Day 14 (Borgesian map)**: In Borges's story "On Exactitude in Science", cartographers draw a map as large as the empire it shows. This is one sheet of that map for Philadelphia: an A4 page at scale 1:1, centred on the letter N of the compass rose in the City Hall courtyard. Print the [PDF](https://github.com/DOGZzl1xy/30DayMapChallenge/blob/main/outputs/day14_borgesian_a4.pdf) at 100% and it covers exactly the ground it shows.

![An A4 map sheet titled Philadelphia, scale 1:1, with a millimetre ruler around the neat line; the map area holds only a few large flat squares of grey and khaki, single pixels of the city's aerial photograph](MAP)

Even the best photograph of the city runs out of detail long before the map reaches the territory: at one metre you can still read the N, but a sheet of paper holds only about 11 pixels.

![Six aerial views zooming in ten times at each step, from 10 km over the city to the compass rose and the letter N, ending with one A4 sheet covering a handful of pixels](MAP2)

Covering the city's 347.9 km² of land would take 5,578,014,222 sheets: a stack 558 km tall, higher than the International Space Station.

![Infographic: 5,578,014,222 sheets; a bar for the 558 km stack beside the International Space Station at 400 km and Mount Everest at 8.8 km; 27,832 tonnes of paper, 177 years to print at one sheet a second, 41 times around the Earth end to end](MAP3)

**How it works:**

- **Sheets**: land area from the 2024 Census Gazetteer divided by 21 × 29.7 cm. Sheets are numbered in rows and columns from the city's north-west corner on a Pennsylvania South (metres) grid: this is row 70,627, column 47,786.
- **Pixels**: every pixel of the city's 2025 aerial survey (3-inch, 7.62 cm) under the sheet is drawn at its true size, read from the original tiles rather than a resampled web map.

**Data sources:**

- City of Philadelphia aerial imagery 2025 (3-inch) via [PASDA](https://www.pasda.psu.edu/), read as [Cloud-Optimized GeoTIFFs on source.coop](https://source.coop/nlebovits/phl-aerial-imagery); 2024 imagery for the wide views via the [PASDA map service](https://services.pasda.psu.edu/server/rest/services/pasda/PhiladelphiaImagery2024/MapServer).
- U.S. Census Bureau [2024 Gazetteer files](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) (land area) and [cartographic boundary files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) (city outline).

**Tools:** Python (rasterio, geopandas, pyproj, matplotlib).
