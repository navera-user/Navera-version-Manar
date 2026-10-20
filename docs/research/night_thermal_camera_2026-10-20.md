# Night thermal camera for NAVERA: options, export rules, fit with STHN

As of 2026-10-20. This is research only, and no code was changed. Every price and spec comes from a page opened on 2026-10-20 (sources at the end). Anything not confirmed on an opened page is marked **(unverified)**.

## 0. Bottom line

- **Best choice: Teledyne FLIR Boson 640 or Boson+ 640 with the 50° HFOV lens, USB, ordered as the 9 Hz version.**
  - It is the same camera family and the same 50° lens used to record the Boson-nighttime dataset that STHN was trained on.
  - The 9 Hz version is ECCN 6A993.a. It needs no US export licence for Tunisia, only an end-use statement.
  - The 30/60 Hz version is 6A003.b.4.b and needs a BIS licence for Tunisia.
  - Price is about US$3.6k (Boson) to US$4.4k–5.8k (Boson+).
- **Second choice: InfiRay (IRay) Micro III Lite 640 with the 6.9 mm lens (62.9° HFOV) and the USB-C board.** It costs about US$1.5k, runs at 50 Hz, is shutterless and has NETD ≤50 mK. It is a Chinese export, and as a generic OEM core it is not in China's UAV-payload control entry. Image quality is lower than the Boson and it has never been tested with STHN.
- **Cheapest smoke test (optional): InfiRay P2 Pro, US$249.** It is 256×192, 56°, 25 Hz and works as a UVC webcam. It is good for testing the ROS/STHN pipeline on a roof or at low altitude. It is not good enough for a real flight test.
- **No visible-light option solves dark open ground.** Low-light CMOS and event cameras both need light. Stars plus an IMU give heading, not position.

## 1. Candidate LWIR cores (comparison table)

| Core | Res / pitch | NETD | HFOV options | Frame rate | Interface | Radiometric | Weight / power | Jetson / ROS 2 support | Indicative price | US / CN export |
|---|---|---|---|---|---|---|---|---|---|---|
| **FLIR Boson 640** (orig.) | 640×512 / 12 µm | ≤40 (Industrial) / ≤50 (Pro) / ≤60 mK (Consumer) | 6, 8, 12, 18, 24, 32, **50 (8.7 mm)**, 95° | 60 Hz (30 selectable) **or 9 Hz version** | CMOS, USB (UVC), MIPI/Camera Link via boards | option | ~7.5 g bare core, ≥600 mW | USB = UVC → V4L2; ROS 2 Humble driver `flir_boson_usb2` (YUV / RAW16) | from US$3,558 (GroupGets) | 60/30 Hz: 6A003.b.4.(a/b) → licence for TN; **9 Hz: 6A993.a → NLR** |
| **FLIR Boson+ 640** | 640×512 / 12 µm | ≤20 (Industrial) / ≤30 mK (Pro) | 4°–95°; 640 list includes **50° (9.2 mm)**, 95° (4.9 mm), 32°, 24°, 18°… | selectable 60, 30, 20, 15, 12, 10, 8.6, 4.3 Hz; 9 Hz export variant | CMOS, **MIPI**, BT.656, **USB3** | select models ("R") | 50° lens: 34.7 g with lens; ≥500–1000 mW | same as Boson (USB/UVC); MIPI needs a custom device-tree driver on Orin (RidgeRun lists Tau, not Boson) | US$4,448 (GroupGets base), 50° lens US$5,542–5,847 (OEMCameras), €5,795 (DE dealer) | same as Boson |
| **FLIR Hadron 640R** | Boson 640R + 64 MP RGB | Boson-class | thermal lens not stated on FAQ | 60 Hz | USB3 + 2-lane MIPI | yes | 56 g, <1.8 W typ. | reference drivers for **Jetson Nano** and Snapdragon RB5 (not Orin) | MSRP US$3,520 | **6A003.b.4.b** (no 9 Hz version found) |
| **FLIR Lepton 3.5** | 160×120 / 12 µm | <50 mK | 57° | **8.6 Hz** ("commercial application exportable") | SPI + I2C (needs PureThermal USB board) | yes | 150 mW (650 mW during 0.5 s shutter) | UVC via PureThermal | low (<US$300) **(unverified)** | 6A993.a, NLR |
| **InfiRay Micro III Lite 640** | 640×512 / 12 µm VOx | ≤50 mK | 4.1 mm 100°, **6.9 mm 62.9°**, 9.1 mm 48.1°, 13 mm 33.5°, 25 mm, 45 mm | **50 Hz** (25 Hz radiometric) | 2-lane MIPI (RAW8), BT.656/1120, LVCMOS, **UVC/USB2 expansion board** | option | <10 g, ≤0.5 W | vendor Windows/Linux/Android SDK; USB-C board shows as UVC; MIPI needs custom driver plus interposer | ~US$1,300–1,520 (Alibaba, MadeInChina listings) | CN: only listed if IFOV <2.5 mrad **and** specially designed for a controlled UAV (9A012.c.1) |
| **InfiRay Tiny1-C / P2 Pro** | 256×192 / 12 µm | <50 mK / ≤40 mK | Tiny1-C 2.0, 3.2, 4.3 mm lenses; P2 Pro 3.2 mm = 56°×42° | ≤25 Hz | Tiny1-C SPI/I2C; **P2 Pro USB-C UVC** | yes | ~0.24–0.35 W, 9 g | P2 Pro is plug-and-play UVC on Linux | P2 Pro **US$249** | IFOV ≈3.8 mrad, so not in the CN UAV list |
| **Guide COIN612(R)** | 640×512 / 12 µm WLP | ≤40 mK | 8.8, 13, 19 mm fixed | 25/30/50/60 Hz | RAW/YUV/BT.656, PAL; RS232 | R version | 22.4 g with 8.8 mm lens, <0.75 W | ARM/Linux SDK; no UVC/MIPI listed | ~US$2,000 (B2B listing) | CN rule as for InfiRay |
| Lynred ATI320/ATI640, Xenics/Exosens Dione, Workswell, Leonardo DRS Tenum 640, Photonis MicroCube 640 | 640 class, 10–12 µm | ~20–50 mK | various | up to 60 Hz | Tenum and MicroCube have MIPI and USB/UVC | – | – | vendor-dependent | quote only | French/EU/US origin, so EU dual-use 6A003 and EAR apply (export class not published, **unverified**) |

Notes:
- **Boson+ FFC:** "Boson+ video output is 'frozen' throughout the 'FFC in progress' state". The last frame is repeated, but the telemetry line keeps updating. The default warning before an FFC ("FFC imminent") is 2 s. Shutterless 640 configurations (part numbers 23640…) exist.
- **Boson+ datasheet EAR99 label:** the "EAR99" marking applies to the document's technology, not to the camera hardware.

## 2. Export control (Tunisian company, Tunisian end user)

**US (EAR, not ITAR).**
- FLIR describes Boson as "NDAA compliant and ITAR free" under Commerce jurisdiction.
- The 6A003.b.4.b control has a decontrol, Note 3.a: "A maximum frame rate equal to or less than 9 Hz". A 9 Hz camera is therefore 6A993.a.
- The DOE export guide says 6A993 cameras "may be exported under No License Required to all countries except terrorist-supporting countries". Tunisia is not one of those.
- GroupGets lists:
  - 60/30 Hz Boson/Boson+/Hadron as **6A003.b.4.b**: licence-free only to AU/CA/UK, "no licence with restrictions" for 33 allied countries, and **licence required for 120 other countries**. Tunisia is not in Country Group A:1, so it falls in that group **(unverified for Tunisia by name)**.
  - 9 Hz versions as **6A993.a**: no licence needed, with a 9 Hz export document.
  - Their policy: "All other international orders will receive a 9Hz camera."
- The 2024 BIS rule (89 FR 13593):
  - 6A003.b.4.b is controlled for NS2/RS2/AT. Cameras over 60 Hz or with more than 111,000 elements, or those embedded in a civil product, are RS1.
  - Even 6A993.a (9 Hz) items need a licence if the end user is military, or if they will go into an 0A919 military commodity.
  - **So a 9 Hz Boson is fine for IRIS civil R&D, but it must not be declared for a military end user without a licence.**
- **Important distributor catch:** GroupGets prohibits "unmanned aerial vehicles (UAVs)" as an end use on every non-US order. That is GroupGets policy (it also bars missile/WMD uses), not a general EAR ban. **Buy from a dealer that accepts a civil UAV R&D end-use statement**, for example the FLIR Europe & Middle East dealer **Acal BFi (UK)**, OEMCameras.com, or a German FLIR dealer. Ask each for its policy in writing.
- **Lead times found:**
  - GroupGets: Boson+ "Out of Stock – Available on Backorder".
  - OEMCameras: "majority of these items in stock".
  - German dealer: 10–20 working days.
  - Add about 1–3 weeks for end-use paperwork and Tunisian customs **(estimate)**.
- **Distributors:** no Teledyne FLIR OEM dealer is listed in Tunisia or North Africa. The Europe & Middle East list has Acal BFi (UK) and Elimec (Israel; not practical for Tunisia). FLIR has a MENA director based in Riyadh.

**EU (dual-use Reg. 2021/821).** Annex I follows the Wassenaar list, so 6A003.b.4.b, including the ≤9 Hz Note 3.a decontrol, should be the same as the US text above **(EU text not opened, unverified)**. An EU reseller shipping a US-origin Boson to Tunisia also stays under the EAR re-export rules. A 60 Hz European core (Lynred, Exosens, Workswell) would need an EU export licence from the seller's country.

**China.**
- MOFCOM Announcement 2024 No. 31 took effect on 2024-09-01. Since 2024-12-01 it is code **9A012.c.1** in the unified dual-use list.
- It controls infrared imaging equipment **specially designed as a payload for controlled UAVs** that has **all** of these: a band of 780–30,000 nm **and IFOV < 2.5 mrad**.
- Generic OEM cores and consumer devices are therefore not listed. Exceptions are the catch-all rules: military end use, WMD, terrorism, or official notice.
- Example IFOVs for the Micro III Lite 640: 4.1 mm = 2.93 mrad (above the threshold), 6.9 mm = 1.74 mrad (below it, but the core is not UAV-specific).
- Ask the supplier to confirm the export status on its invoice. Alibaba lead time is 30 days.

## 3. Fit for NAVERA

**What STHN was trained on.**
- The STGL/STHN Boson-nighttime dataset was recorded with a **FLIR Boson, 640 px, 8.7 mm lens, 50° HFOV**, nadir view, at about **1 m/px**. That implies about 690 m AGL.
- There were six flights between 21:00 and 04:00, covering about 33 km², against Bing (Maxar) imagery.
- The STHN queries are **512×512 px crops at ~1 m/px (≈512 m footprint), 8-bit**, resized to 256 px inside the model. The best result was about 12 m centre error (two-stage, WS=1536).
- Most of the data is real Boson imagery plus synthetic thermal images made by TGM from satellite tiles. **This favours a Boson 640 50°**: same sensor, same AGC look, same noise and same lens geometry. The papers do not state polarity. Boson defaults to white-hot, and NAVERA's `night_pkg` already tests that inverted (black-hot) images still give NCC >0.5.

**Footprint against altitude.** The ground width is 2h·tan(HFOV/2). NAVERA's `normalize_query` resamples the frame to map scale using altitude and HFOV.

| HFOV | 100 m | 300 m | 500 m | 1000 m | 1500 m | Lowest altitude for ≥500 m width |
|---|---|---|---|---|---|---|
| 50° (Boson) | 93 m | 280 m | 466 m | 933 m | 1.40 km | **~540 m** |
| 62.9° (InfiRay 6.9 mm) | 122 m | 367 m | 612 m | 1.22 km | 1.84 km | **~410 m** |
| 75° (NAVERA test) | 153 m | 460 m | 767 m | 1.53 km | 2.30 km | **~330 m** |
| 95° (Boson 4.9 mm) | 218 m | 655 m | 1.09 km | 2.18 km | 3.27 km | **~230 m** |

- The vertical side is about 80% of the width on a 640×512 sensor, so a square crop needs about 20% more altitude.
- **Below about 300–500 m AGL no lens gives STHN its ≥500 m footprint.** A 95° lens adds strong distortion and a different look from the 50° training data.
- At 1500 m with 640 px the ground resolution is about 2.2 m/px (50°). That is still fine, because the model works at 256 px (~2 m/px) internally.
- **Practical choice: 50° to match the training data, flown at ≥550–700 m AGL. Fall back to 63–75° if the mission must work lower.**

**Frame rate.**
- 9 Hz is enough. STHN runs at 35–64 ms per inference on a GPU, and map matching is a slow absolute fix fused with the IMU.
- At 30 m/s and 1 m/px, frames are 3.3 m apart. Blur from the ~8 ms thermal time constant is about 0.25 px.
- 9 Hz is the price of licence-free export, not a technical limit.

**Shutter / NUC.**
- During an FFC the shuttered Boson repeats the last frame. The default warning before an FFC is 2 s.
- NAVERA should either read the FFC state from the telemetry line (or the "FFC imminent" flag) and drop repeated frames, or switch to manual FFC mode and trigger FFC between matches.
- Shutterless cores (InfiRay, Boson+ 23640) avoid the freeze, but their non-uniformity drifts. FLIR recommends a periodic shutter anyway.

**Polarity / bit depth.**
- Record RAW16 (`flir_boson_usb2` RAW16 mode). `night_pkg` already contrast-stretches mono16 to 8-bit, which means the AGC is under NAVERA's control rather than the camera's.
- Use white-hot by default, and check the histogram against a few Boson-nighttime samples.

## 4. Alternatives if thermal is not possible

- **Low-light visible (Sony STARVIS IMX462 / IMX585 on Jetson).** e-con e-CAM22_CUONX (IMX462, MIPI, Orin NX/Nano, JetPack 6.1 driver). Arducam Darksee IMX462 US$153.99, IMX585 US$249.99.
  - These work under city lights or moonlight.
  - On moonless open ground in Tunisia there are too few photons. The "0 lux" claim on the vendor page is marketing.
  - Night lights also do not match daytime satellite maps. **Honest verdict: useful near towns, not a general night solution.**
- **Stars plus inertial only.**
  - A star camera gives very good attitude and heading. A position fix needs a precise local vertical: 1 arcminute of vertical error is about 1 nmi (1.85 km). With a MEMS-level horizon of about 0.1°, that is about 11 km **(geometry; standard 1 arcmin = 1 nmi)**.
  - Between fixes, position comes from dead reckoning. Low-cost MEMS INS "rapidly degrades within minutes" without aiding (DTIC/NDIA). Tactical-grade drift of about 1 km per 30 min is cited by aggregators **(unverified)**.
  - **Honest verdict: stars plus IMU limit heading drift, but position error still grows to hundreds of metres to kilometres per hour of flight.** That is acceptable only for short night legs between day or thermal fixes.
- **Event cameras.** They are visible-band, need scene motion and light, and give "essentially no output" for a static scene. Night UAV research exists (Cranfield mutual-information matching, NightSight active illumination preprint), but nothing is a product. **Not a replacement for thermal.**

## 5. Recommendation and what to buy for one real night test

1. **Camera:** FLIR **Boson 640, 50° HFOV (8.7 mm), USB, 9 Hz export version**. Boson+ 640 50° (22640AS50) is the upgrade (≤30 mK, newer AGC) if the budget allows.
   - Ask for the shuttered version.
   - Order through a dealer that accepts a civil UAV R&D end-use statement (Acal BFi UK, OEMCameras, or an EU FLIR dealer). Not GroupGets, because they bar UAV use.
   - Budget about US$3.6–6k plus shipping and duties.
2. **Interface:** the Boson USB kit (USB-C backend / VPC board) so the camera appears as UVC on the Orin. Run `flir_boson_usb2` in RAW16 mode on ROS 2 Humble. **Confirm the dealer includes the USB board, since the core ships without interfaces.**
3. **Mount:** rigid nadir mount, with the camera/IMU extrinsics measured. Log RAW16, the FFC telemetry, IMU, barometric altitude and RTK/GPS ground truth to a rosbag.
4. **Flight:** a moonless night over an area cached in the offline map. Fly ≥600 m AGL for the 50° lens (or ≥350 m with a wider lens). Also make one pass at 300–400 m to find where matching breaks down.
5. **Second choice:** InfiRay Micro III Lite 640 with 6.9 mm lens and USB-C board (~US$1.5k, about 30 days from China).
6. **Pre-test (optional):** InfiRay P2 Pro (US$249, UVC) to rehearse the driver, recording and STHN pipeline before the Boson arrives.

## Sources (opened 2026-10-20)

- Boson+ datasheet (Acal BFi PDF, published 2026-09-16): https://www.acalbfi.com/nl/file/16133/Boson-Plus-Product-Datasheet-Rev-114.pdf
- FLIR Boson product page: https://oem.flir.com/products/boson/
- FLIR Lepton page: https://oem.flir.com/products/lepton/
- Hadron 640R FAQ: https://oem.flir.com/learn/discover/faq---everything-you-need-to-know-about-hadron-640r/
- FLIR dealer list: https://oem.flir.com/contact/find-a-dealer/
- GroupGets export page: https://groupgets.com/pages/exportcontrol
- GroupGets Boson+ 640: https://groupgets.com/products/boson-plus
- GroupGets Boson collection: https://groupgets.com/collections/boson
- OEMCameras Boson+ 50°: https://www.oemcameras.com/products/22640as50-htm
- German FLIR dealer: https://www.flir-infrarotkameras.de/Products/Thermal-Imagers-for-drones-thermal-Kopter-solutions
- BIS 2024 rule, 89 FR 13593 (Note 3, RS columns): https://www.federalregister.gov/documents/2024/02/23/2024-03661/revision-of-license-requirements-of-certain-cameras-systems-or-related-components
- eCFR Supp. 6 to Part 774: https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%206%20to%20Part%20774
- DOE export guide (6A993, 9 Hz): https://hrp.doe.gov/Document/DocView/34
- MOFCOM Announcement 2024 No. 31: https://www.mofcom.gov.cn/zcfb/zgdwjjmywg/art/2024/art_61ef7953cb4c49bd998822a57a09c8e7.html
- 9A012.c.1 analysis: https://www.10100.com/article/149204049
- InfiRay Micro III Lite 640 page: https://www.irayimage.com/products/micro-iii-lite-640-uncooled-micro-thermal-camera-core.html
- InfiRay Micro III Lite 640 manual (lens table): http://liberal-technology.com/wp-content/uploads/2024/07/Xcore-Micro%E2%85%A2-Lite-Series-640%C3%97512-Uncooled-Thermal-Imaging-Module-Product-Manual.pdf
- InfiRay Micro III Lite 640 Alibaba price: https://www.alibaba.com/product-detail/InfiRay-Thermal-Imaging-Cameras-Xcore-M3S601101312X00NPX_1601387486598.html
- InfiRay P2 Pro: https://www.infiray.com/p2-pro-thermal-camera-for-smartphone
- Hackaday P2 Pro review (UVC on Linux): https://hackaday.com/2023/06/19/review-infiray-p2-pro-thermal-camera/
- Tiny1-C: https://www.infiray.com/products/tiny1-c-micro-uncooled-ir-camera-sensor-module.html (site blocked direct fetch; specs taken from the search extract)
- Guide COIN612: https://www.machineryoffers.com/offer/36051-Mini-Size-High-Resolution-640x512-Thermal-Imaging-Camera-Module-For-Temperature-Measurement-with-Excellent-Quality-Image.html
- STGL / Boson-nighttime paper: https://arxiv.org/html/2306.02994
- STHN paper: https://arxiv.org/html/2405.20470v3
- STHN repository: https://github.com/arplaboratory/STHN
- ROS 2 Boson driver: https://github.com/akhilj95/flir_boson_usb2
- ROS 1 Boson driver: https://wiki.ros.org/flir_boson_usb
- RidgeRun V4L2 driver list: https://developer.ridgerun.com/wiki/index.php/JetsonTX2/V4L2_driver_support/V4L2_drivers_available_for_Jetson_SoCs
- e-con IMX462 for Orin: https://www.e-consystems.com/nvidia-cameras/jetson-orin-nx-cameras/sony-starvis-imx462-ultra-lowlight-camera.asp
- Arducam Darksee: https://www.arducam.com/blog/product/arducam-xisp-darksee-pre-tuned-isp-2mp-low-light-mipi-camera-for-nvidia-jetson-orin-nx-orin-nano/
- MEMS INS drift (DTIC/NDIA): https://ndia.dtic.mil/wp-content/uploads/2005/psts/brown.pdf
- Event-camera night navigation (Cranfield): https://dspace.lib.cranfield.ac.uk/handle/1826/20570
- Event cameras need motion: https://spectrum.ieee.org/drone-with-event-camera-takes-first-autonomous-flight
