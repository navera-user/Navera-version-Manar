# Map imagery: licences, resolution cost, labelled sources (2026-10-21)

Branch `work/map-source-2026-10-21`. This is a risk summary to inform decisions, **not legal
advice**. Licence texts were opened on 2026-10-21 and quoted where they were read (PDF text
extracted). Anything that could not be opened is marked **not verified**.

## 1. Bottom line

- **What NAVERA does today is not permitted.** It downloads Esri World Imagery tiles anonymously
  from `server.arcgisonline.com`, stores them in MBTiles and reads them with its own matcher.
  The Esri Master Agreement (E204CW, revised 2025-08-01) §3.2(c) says: "Customer may take Online
  Services basemaps offline through Esri Content Packages and subsequently deliver (transfer) them
  to any device for use with licensed ArcGIS Runtime applications and ArcGIS Desktop. Customer may
  not otherwise scrape, download, or store Data." §3.2(a) adds "Customer may only use Data with
  the Products for which Esri has provided the Data." World Imagery also contains Vantor (Maxar)
  content. A map built from it must not ship on a sold device, and it should not be on demo units
  that leave IRIS.
- **The free, legally clean imagery is 10 m** (Copernicus Sentinel-2 and products built from it).
  Commercial use, offline storage and preloading on sold devices are all allowed with the
  attribution "Contains modified Copernicus Sentinel data [year]".
- **10 m does not work for NAVERA's day matcher at the heights measured (460–780 m above
  ground).** On real drone photos it accepts 0–0.4 % of frames with simulated 10 m maps and **0 %
  with real Sentinel-2 L2A** (section 3). 2 m costs almost nothing (87 % accepted vs 90 %), 3 m
  keeps 75 % on textured ground from ~450 m, and 5 m is marginal (33 %). The finest free source is therefore not
  enough for a product at these heights; it can serve as a coarse fallback or for high flights
  only (extrapolation, section 3.4).
- **A ~1 m product map needs a negotiated commercial licence.** The best fit is Airbus (its
  standard EULA allows storage on internal devices and explicitly allows ML; the export and
  transfer clause must be negotiated). Alternatively, the customer buys the imagery licence in
  its own name and NAVERA only processes customer-supplied imagery (`--source geotiff`).

## 2. Licences (as of 2026-10-21)

| Source | Res | Coverage TN / world | Offline storage on a commercial device | Preload / redistribute to customers | Attribution | Cost | Freshness | Defence / export notes | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Copernicus Sentinel-2 L2A** (AWS COGs via earth-search, or CDSE) | 10 m RGB | Yes / all land | **Yes** (EU Reg. 1159/2013: free, full, open) | **Yes** ("reproduction; distribution; … adaptation") | "Contains modified Copernicus Sentinel data [year]" | Free (AWS: no account; CDSE: free account) | ~5-day revisit; on AWS within hours | Limits only "in rare cases of security concerns" | **Use (free tier); implemented** |
| CDSE Sentinel-2 Global Mosaics (quarterly) | 10 m | Yes / all, since 2020 | Yes | Yes | Same | Free (CDSE account) | Quarterly, cloud-filtered | Same | Good free basemap (not implemented: account) |
| ESA WorldCover S2 RGBNIR composites 2020/2021 | 10 m | Yes / all | Yes (CC BY 4.0) | Yes | CC BY citation (exact string not verified) | Free (AWS, no account) | Fixed: 2020, 2021 | none found | Free fallback (older) |
| EOX Sentinel-2 cloudless 2016 | 10 m | Yes / all | Yes (CC BY 4.0) | Yes | Required | Free data; **public WMTS may not be used for commercial production** | 2016 | not verified | Data OK; download not from the public WMTS |
| EOX cloudless 2018–2025 | 10 m | Yes / all | No under CC BY-NC-SA; **yes** with the commercial licence ("packaging tiles for offline use … flight tablets") | Commercial licence: unlimited end users; no standalone resale | Required | €5,000 per vintage (2018–24), €6,000 (2025), perpetual; +€1,000 MBTiles | Annual | not verified | Paid 10 m option (does not solve the resolution problem) |
| Landsat 8/9 (USGS) | 30 m (15 m pan) | Yes / all | Yes | Yes ("used or redistributed as desired") | Source statement requested | Free | 8 days (combined) | none | Too coarse |
| **Esri World Imagery** (current default) | ≤ 1 m | Yes / all | **No**, except Esri Content Packages inside licensed ArcGIS Runtime / Desktop apps | **No** | Esri + providers (incl. Vantor) | ArcGIS account; Location Platform tiles: 2 M free/month then $0.15 per 1,000 | Mixed dates | EAR; OFAC; no missile/nuclear/chemical/biological end uses | **Development only; stop shipping** |
| Vantor (ex-Maxar), incl. Vivid | 15–50 cm | Yes / all | Internal Use only | **No** without a Group / add-on licence | "[Product] © [year] Vantor" | Vivid ≈ $12–15/km² (reseller, indicative) | Archive + tasking | EAR / ITAR / OFAC; **bans AI/ML use** unless the order authorises it; "not certified as flight or avionics navigation software" | Paid; needs custom terms |
| **Airbus** (Pléiades / SPOT / OneAtlas Basemap) | 0.3–0.5 m / 1.5 m | Yes / all | **Yes** ("store … in any internal device") | **No** transfer to third parties, **nor "outside of the territory"**, unless Airbus authorises | "© CNES (year), Distribution Airbus DS" / "© Airbus DS (year)" | Pléiades archive ≈ $25/km² (reseller, indicative); Basemap min. 2,500 km² | Daily-capable | **ML explicitly allowed** (§1.1(e)) | **Best paid fit; negotiate §1.2(a)** |
| Planet (PlanetScope / Basemaps) | 3 m | Yes / all | Internal use | **No** for imagery without a "License Upgrade"; derivative products without image data are free | Required | Quote only | Near-daily | Export compliance; delete on termination | Mid tier: 3 m measured below |
| Planet NICFI | 4.77 m | **No** (30°N–30°S; ended 2025-01-24) | — | — | — | — | — | — | Not applicable |
| Tunisia OTC orthophotos | not verified | Tunisia | not verified | not verified | not verified | not verified | not verified | Aerial photography needs a Defence/Interior-reviewed permit | Ask OTC |
| Mapbox Satellite | sub-metre | Yes / all | **No** (cache ≤ 30 days, SDK only) | **No** | Required | Usage-based | Mixed | Use in "aerial, manned and unmanned vehicles" needs a separate licence; no AI/ML | Excluded |
| Bing / Azure Maps | sub-metre | Yes / all | **No** ("may not … save the 'raw' data (tiles)") | **No** | Required | Usage-based | Mixed | Bans "automatic or autonomous vehicle control" | Excluded |
| Google Maps Platform | sub-metre | Yes / all | **No** (no pre-fetch, storage or bulk download) | **No** | Required | Usage-based | Mixed | Bans embedded-vehicle devices, ITAR use, "High Risk Activities" | Excluded |
| OpenAerialMap | varies | **Effectively none in Tunisia** (API, bbox 7.5,30.2,11.6,37.6: 3 entries at ~30 m and 278 m) | Yes (CC BY 4.0) | Yes | CC BY | Free | — | — | Implemented; useless for Tunisia |
| Satellogic EarthView | 1 m | Scattered 384 m patches, 2022 | Yes (CC BY 4.0) | Yes | CC BY | Free | Static | — | Training data, not a map |

### Sources read (key clauses)

- Copernicus Sentinel data legal notice (PDF read in full):
  https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice. "free, full
  and open access"; free use includes "(a) reproduction; (b) distribution; (c) communication to the
  public; (d) adaptation, modification and combination"; distribution of modified data must say
  "Contains modified Copernicus Sentinel data [Year]". No commercial-use restriction.
- CDSE terms: https://dataspace.copernicus.eu/terms-and-conditions. §4: users "need to register as
  a user" (free account). The §3 bans on non-commercial use, resale and derivatives concern portal
  material, not Sentinel data.
- AWS open data: https://registry.opendata.aws/sentinel-2-l2a-cogs/ ("No AWS account required");
  STAC https://earth-search.aws.element84.com/v1. **This is the access path implemented: it was
  used without any account on 2026-10-21.**
- CDSE Global Mosaics: https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-global-mosaics
  (B04/B03/B02/B08, gsd 10, quarterly, since 2020-01-01; licence link points to the Sentinel legal
  notice).
- EOX cloudless: https://cloudless.eox.at/documentation/faq,
  https://cloudless.eox.at/documentation/license. The 2016 vintage is "published under the CC BY 4.0
  license"; 2018 and later need "a paid commercial license"; "Using the public WMS/WMTS endpoints for
  commercial production apps is strictly prohibited."
- Landsat: https://www.usgs.gov/faqs/are-there-any-restrictions-use-or-redistribution-landsat-data
- ESA WorldCover: https://esa-worldcover.org/en/data-access (CC BY 4.0; S2 RGBNIR composites
  2020/2021).
- Esri: Master Agreement E204CW PDF
  https://assets.esri.com/content/dam/esrisites/en-us/media/legal/ma-translations/english.pdf
  (§3.2(a), §3.2(c), §3.3(a), export §B.7.3). World Imagery item metadata
  (https://www.arcgis.com/sharing/rest/content/items/10df2279f9684e4a9f6a7f08febac2a9?f=json): "not
  intended to be used to export tiles for offline". The "World Imagery (for Export)" item
  (226d23f076da478bba4589e7eae95952) is for "ArcGIS applications and apps built with an ArcGIS Runtime
  SDK": NAVERA's matcher is neither. Pricing: https://location.arcgis.com/pricing/
- Vantor Internal Use License WW0023F, 2025-10-01 (PDF):
  https://cdn.sanity.io/files/ava0h2e5/production/968c5e922eefe6c454a9a0cdf3378b71112a2ccf.pdf;
  add-ons: https://vantor.com/legal/ (Background Layer licence **not read**).
- Airbus Standard EULA, November 2025 (PDF):
  https://storage.googleapis.com/p-ssp-iep-prod-8ff-strapi-uploads/Standard_End_User_Licence_Agreement_November_2025_e87587e010/Standard_End_User_Licence_Agreement_November_2025_e87587e010.pdf
  §1.1(a) "store … in any internal device"; §1.1(e) machine learning allowed; §1.2(a) no transfer
  "to any third party … nor transfer outside of the territory of its establishment, unless expressly
  authorised by AIRBUS DS". Index: https://www.space-solutions.airbus.com/legal/licences/
- Planet EULA (PDF): https://assets.planet.com/docs/upload-EULA-us.pdf ("To redistribute Content or
  VAPs for commercial purposes … you must request additional licensing"; whether it applies to
  Basemaps is **not verified**).
- Tunisia: https://www.otc.nat.tn/ (orthophoto specifications **not verified**); aerial photography
  permit https://idaraty.tn/fr/procedures/autorisation-de-prises-de-vues-des-photos-aeriennes
  (arrêté of 1995-04-06; National Defence review; valid one month). This permit may also apply to
  NAVERA's own camera flights in Tunisia.
- Mapbox product terms: https://www.mapbox.com/legal/product-terms (§1.9, §2.8.1, §1.5, §1.2.2).
- Azure Maps / Bing: https://www.microsoft.com/licensing/terms/productoffering/MicrosoftAzure/MCA
- Google Maps Platform: https://cloud.google.com/maps-platform/terms
- OpenAerialMap: https://api.openaerialmap.org/meta?bbox=7.5,30.2,11.6,37.6 (queried live).

**Not verified:** Vantor Background Layer / Group licences, Airbus Background Layer licence, Planet
Basemaps terms, OTC orthophotos, the exact WorldCover attribution string, EOX defence terms, Esri
Wayback, Earth Engine terms, any price not listed above.

## 3. What resolution costs: day accuracy vs map resolution (measured)

### 3.1 Method

- **Data:** the 8 real UAV-VisLoc drone flights already used in `docs/VALIDATION_STATUS.md` ("Day: real
  drone flights"). Same conventions: NAVERA's day matcher (`LearnedMatcher`, DISK + LightGlue), a prior
  250 m off in a random direction (search 350 m), the product position path with
  `pose_tilt_guard_deg` 4, the per-flight fitted field of view, the height above ground from the DEM,
  and photos 06_0099–06_0180 excluded. Every 3rd photo is used (`--stride 3`).
- **Degraded maps** (`navera_tools/bench/degrade_map.py`): the dataset's own map (z17, ~1.0 m/px) is
  reduced to 2 / 3 / 5 / 10 m per pixel by pixel averaging (each coarse pixel is the mean of the
  ground it covers), with no extra blur. It is then enlarged back to the z17 grid (bicubic), so the
  matcher is unchanged and the map simply holds no finer detail. This is how a coarse source is
  stored by `tile_sources` (resampled to z17). Real sensor optics are softer than a box average, so
  these results are **optimistic** for real 3–10 m imagery.
- **Real Sentinel-2 L2A** (`navera_tools/bench/sentinel2_area.py`, through the product code
  `tile_sources.fetch_tiles`, no account):
  - flight 11 (Shandan, flown 2023-10-19): two **same-day** scenes, S2A_47SPC/47SPD_20231019;
  - flight 03 (Taizhou, flown 2018-10-23): S2A_50SQA_20181011, 12 days earlier.
  - Visual check: features such as pylons and tracks line up with the native map to within a pixel
    (10 m).
- **Native reference:** the full native runs of 2026-10-20 (`f*_guard4.json`), reduced to the same
  photos (every 3rd). Their random prior directions differ from the new runs.
- **Results:** `~/.navera_sim/uavvisloc/resolution/` (`g<gsd>_f<flight>.json`, `s2_f<flight>.json`,
  `table_2026-10-21.txt`). Table: `navera_tools/bench/resolution_table.py`.
- **Coverage:** 2 m and 5 m were run on the three flights where the native map works well (03, 04,
  11), because GPU time was shared with other agents. 3 m was run on all 8 flights, 10 m on 3 flights
  and real Sentinel-2 on 2 flights.

"Footprint px" is the camera's ground footprint width divided by the map resolution
(2 h tan(hfov/2) / gsd): how many map pixels the matcher gets to work with.

### 3.2 Results per flight

| Map | Flight | Height AGL | Footprint px | Photos | Accepted | Error median / p90 / max (m) | > 100 m |
|---|---|---|---|---|---|---|---|
| native ~1 m | 03 | 462 m | 451 | 256 | 232 (91 %) | 12.5 / 23 / 51 | 0 |
| native ~1 m | 04 | 539 m | 526 | 246 | 220 (89 %) | 13.6 / 39 / 81 | 0 |
| native ~1 m | 11 | 778 m | 862 | 197 | 180 (91 %) | 21.8 / 39 / 75 | 0 |
| 2 m | 03 | 462 m | 226 | 256 | 215 (84 %) | 11.5 / 23 / 45 | 0 |
| 2 m | 04 | 539 m | 263 | 246 | 219 (89 %) | 15.5 / 37 / 81 | 0 |
| 2 m | 11 | 778 m | 431 | 197 | 175 (89 %) | 22.6 / 40 / 74 | 0 |
| 3 m | 03 | 462 m | 150 | 256 | 161 (63 %) | 12.1 / 26 / **278** | **1** |
| 3 m | 04 | 539 m | 175 | 246 | 209 (85 %) | 15.0 / 39 / 81 | 0 |
| 3 m | 11 | 778 m | 287 | 197 | 156 (79 %) | 21.1 / 39 / 81 | 0 |
| 5 m | 03 | 462 m | 90 | 256 | 37 (14 %) | 17.3 / 26 / 57 | 0 |
| 5 m | 04 | 539 m | 105 | 246 | 149 (61 %) | 19.9 / 47 / **113** | **1** |
| 5 m | 11 | 778 m | 172 | 197 | 42 (21 %) | 25.1 / 47 / 84 | 0 |
| 10 m | 03 | 462 m | 45 | 256 | 0 (0 %) | — | 0 |
| 10 m | 04 | 539 m | 53 | 246 | 1 (0.4 %) | 33.6 | 0 |
| 10 m | 11 | 778 m | 86 | 197 | 0 (0 %) | — | 0 |
| **real Sentinel-2 L2A** | 03 | 462 m | 45 | 256 | **0 (0 %)** | — | 0 |
| **real Sentinel-2 L2A** | 11 | 778 m | 86 | 197 | **0 (0 %)** | — | 0 |

**3 m on the flights where the native map matches poorly** (all 8 flights at 3 m):

| Flight | Height | native accepted | 3 m accepted | 3 m median / p90 / max |
|---|---|---|---|---|
| 10 | 293 m | 2 / 48 (4 %) | 2 (4 %) | 21.0 / 22 / 22 |
| 06 | 308 m | 67 / 88 (76 %) | 52 (59 %) | 17.2 / 30 / 49 |
| 05 | 376 m | 16 / 158 (10 %) | 10 (6 %) | 18.9 / 32 / 70 |
| 01 | 387 m | 61 / 273 (22 %) | 22 (8 %) | 19.2 / 37 / 52 |
| 08 | 549 m | 94 / 345 (27 %) | 33 (10 %) | 19.1 / 48 / 65 |
| **All 8** | | **872 / 1611 (54 %)** | **645 (40 %)** | 1 fix > 100 m |

### 3.3 Pooled over flights 03, 04 and 11 (699 photos)

| Map | Accepted | Error median / p90 / max (m) | > 100 m |
|---|---|---|---|
| native ~1 m | 632 (90 %) | 14.7 / 33 / 81 | 0 |
| 2 m | 609 (87 %) | 15.5 / 34 / 81 | 0 |
| 3 m (Planet-like) | 526 (75 %) | 15.6 / 36 / 278 | 1 |
| 5 m | 228 (33 %) | 20.2 / 45 / 113 | 1 |
| 10 m (Sentinel-2-like) | 1 (0.1 %) | 33.6 | 0 |
| real Sentinel-2 (flights 03 and 11, 453 photos) | **0 (0 %)** | — | 0 |

### 3.4 Reading

- **2 m costs almost nothing:** 87 % accepted against 90 %, with the same error.
- **3 m keeps NAVERA useful on textured ground at 460–780 m** (63–85 %, median error unchanged at
  12–21 m), but:
  - it loses more where matching is already hard (flights 01, 05, 08: native 10–27 % drops to 6–10 %);
  - it produced one **wrong fix hidden by its stated accuracy**: 03_0013, a wrong place with 14
    inliers, 278 m off with a stated sigma of 25 m. The native map placed the same photo within
    14 m with 34 inliers.
- **5 m is marginal** (14–61 %). It also produced one fix 113 m off: 04_0625, a pose error at 9.6°
  tilt where the frame centre was 77 m off. The native map put that photo 17 m off with 181 inliers.
- **10 m (Sentinel-2) does not work at these heights.** It gives 0–0.4 % in simulation and **0 % on
  real same-day Sentinel-2**. Every rejection is "too few feature matches / inliers", so the gate
  fails safe: no wrong fix is published.
- **The coarsest useful resolution measured is 3 m, at ≥ ~450 m above ground** with the dataset's
  ~52–58° lens (footprint ≥ ~150 px). 2 m is safe from ~300 m.
- **Rule of thumb from these runs:** the footprint needs about **≥ 175–290 map pixels** for ~80 %
  acceptance on textured ground, ~100–150 px for ~15–60 %, and < 90 px gives ≤ 21 %. This depends on
  the terrain: flight 11 at 172 px gave 21 %, flight 04 at 175 px gave 85 %.
- **Extrapolation for 10 m (not measured, flagged):** reaching 200–300 px on a 10 m map needs a
  2–3 km wide footprint. That means ~2–3 km above ground with a 52–58° lens, or ~700–1,000 m with
  NAVERA's wide camera (the Insta360 crop is capped at 111°: footprint ≈ 2.9 × height). This assumes
  ground texture at 10 m scale behaves like texture at 1–3 m scale, which the real Sentinel-2 runs
  could not test (the UAV-VisLoc photos are all below 800 m). **Before Sentinel-2 is offered for high
  flights, it must be measured on real high-altitude or wide-angle frames.**
- **Coarse maps raise the wrong-fix risk.** Fewer inliers on a blurrier map make wrong places
  easier to fit, and the matcher's sigma does not grow with map resolution beyond `mpp_map × level`.
  A coarse product map would need the stated sigma (and the 30 m floor) re-scored on it.

### 3.5 Storage

Sentinel-2 resampled to z17 JPEG costs ~0.16–0.3 MB/km². The flight 11 area is 532 tiles, ~30 km²:
4.8 MB against 17.6 MB for the native ~1 m map. Storing Sentinel-2 at its native zoom 14 instead
would be ~64× fewer tiles, but the day matcher reads z17 only.

## 4. Recommendation

- **Now:**
  - keep Esri World Imagery as the **development and simulator default only**. It is now labelled
    `esri_world_imagery`, dev-only, and every map built from it carries a licence warning in
    `area.json`;
  - do not ship or demo outside IRIS a device holding Esri tiles, including the delivered Sousse
    map (it is unlabelled, so it is flagged as presumed Esri).
- **Free tier (development, demos, and a legally clean baseline):**
  - Copernicus Sentinel-2 L2A (`--source sentinel2_l2a`, implemented, no account), or the CDSE
    quarterly mosaics (account needed, not implemented);
  - legally clean everywhere (Tunisia, MENA, worldwide), free and fresh, but **measured useless for
    day matching at 300–800 m** (0 %);
  - keep it for coverage checks, mission planning displays and very high flights after a dedicated
    measurement.
- **Paid tier (product):** a **≤ 2–3 m** source, preferably **≤ 1.5 m**, under a licence that
  allows offline storage on sold devices and export:
  1. **Airbus** (Pléiades 0.5 m / SPOT 1.5 m; OneAtlas Basemap). Its EULA already allows internal
     storage and ML. Negotiate the §1.2(a) third-party / export clause (an OEM or multi-end-user
     licence naming the destination countries). SPOT 1.5 m sits between the 1 m and 2 m points
     measured above (≥ 87 % accepted), so it would cost almost no accuracy.
  2. **Customer-licensed imagery:** the customer buys imagery in its own name (common for defence
     customers). NAVERA imports it with `--source geotiff` and records the contract in the map's
     licence fields.
  3. Vantor (needs written AI/ML and redistribution permission; EAR/ITAR exposure) or Planet 3 m
     (needs a licence upgrade for redistribution; 3 m measured at 75 % accepted on textured ground,
     with one hidden wrong fix in 526).
- **Tunisia:** ask OTC for orthophoto licensing. Also check the Defence-reviewed aerial photography
  permit for NAVERA's own camera flights.

## 5. Code (branch `work/map-source-2026-10-21`)

### `day_pkg/day_pkg/tile_sources.py` (new): licence-labelled sources

The API for the offline-bundle tool:

```python
from day_pkg.tile_sources import fetch_area, read_map_info, licence_warnings, SOURCES
path = fetch_area((min_lon, min_lat, max_lon, max_lat), "sentinel2_l2a", "/data/maps/area.mbtiles",
                  zoom=17, date="2026-06-01/2026-10-21", max_cloud=5, progress=cb)   # -> path
info = read_map_info(path)     # source, licence, attribution, offline_commercial, resolution_m, imagery_date, scenes
licence_warnings(info)         # [] when the map may ship on a sold device
fetch_tiles(tiles, 17, source, out_path, ...)     # the same for a tile list (prepare_area's corridor)
```

- **bbox order:** GeoJSON/STAC (min_lon, min_lat, max_lon, max_lat). A swapped order raises an
  error.
- **Sources in `SOURCES`:**
  - `esri_world_imagery`: dev-only, `offline_commercial=no`;
  - `sentinel2_l2a`: earth-search STAC + AWS COGs, no account, `yes`;
  - `openaerialmap`: CC BY 4.0, finest image over the area, `yes`;
  - `geotiff`: bought imagery, `path=` plus `licence=` / `provider=`, `per-contract`;
  - `custom`: any XYZ `url=`, licence `unknown`.
- **Metadata:** each MBTiles gets standard metadata (`name`, `format`, `bounds`, `minzoom`,
  `maxzoom`, `attribution`, `description`) and `navera_source`, `navera_licence`,
  `navera_licence_url`, `navera_offline_commercial`, `navera_dev_only`, `navera_resolution_m`,
  `navera_imagery_date`, `navera_scenes`, `navera_created`.
- **One file, one source:** adding tiles of another source (or another custom URL) raises
  ValueError, so a map's licence label stays honest. An unlabelled old cache is adopted.
- **No new dependency:**
  - Sentinel-2 is read through HTTP range requests with a minimal 8-bit GeoTIFF/COG reader
    (tiled or stripped, deflate, predictor 2, BigTIFF), checked bit-identical against `tifffile` on
    a real COG;
  - UTM is projected with the Krüger series, checked against pyproj to < 0.1 mm;
  - scenes are picked greedily to cover the area (least cloud first), with no-data masked.
- **Other source types:** coarser XYZ sources are over-zoomed from their native zoom; bought
  GeoTIFFs in EPSG 4326 / 3857 / UTM are resampled bicubically to z17.

### `prepare_area.py` (minimal, outside `prepare()` except two lines)

- `--source NAME` (instead of `--fetch-url`; needs `--cache`). A base map labelled with another
  source is not mixed in.
- Every download cache is labelled: a `--fetch-url` is recognised as Esri (dev-only) or `custom`.
- `area.json` gains `map_source` and `licence_warnings`.

### Other changes

- **Simulator:** `navera_tools/sim/vision_link.py` marks the Esri `TILE_URL` default as
  development-only (comment only, no behaviour change).
- **Bench tools:**
  - `navera_tools/bench/degrade_map.py`: simulated coarse maps;
  - `navera_tools/bench/sentinel2_area.py`: a real Sentinel-2 area through the product path;
  - `navera_tools/bench/resolution_table.py`: the tables above.
- **Tests:** `day_pkg/test/test_tile_sources.py` (11 tests, no network: local HTTP tile server,
  synthetic GeoTIFFs) and one new test in `test_prepare_area.py` (labelled cache, mixed sources
  refused). Result: 20 passed together with the existing `test_prepare_area.py`; 49 passed including
  `simulation_web/test/test_mission_prep.py`.

### Not done / next

- `simulation_web/mission_prep.py` still passes `--fetch-url $NAVERA_TILE_URL`. Passing
  `--source $NAVERA_TILE_SOURCE` there is a one-line change, left to the map-bundle work so that both
  branches don't edit that file.
- No cloud mask from the Sentinel-2 SCL band yet (only scene-level cloud < 5 %).
- CDSE mosaics and ESA WorldCover composites are not implemented as sources.
- The stated sigma has not been re-scored on coarse maps (see 3.4).
- 2 m and 5 m were measured only on the 3 textured flights. High-altitude or wide-angle frames on
  Sentinel-2 are not measured.
