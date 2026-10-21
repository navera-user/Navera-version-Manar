# NAVERA — Target standards: what they would demand, and the gap

Status 2026-10-21. A brief planning note, not a compliance claim: NAVERA has no certification
basis agreed with an authority yet. The first step for any of the routes below is that agreement
(the operation, the vehicle class, and whether NAVERA is installed equipment or part of a
certified UAS). Standard names and editions should be confirmed with the authority / notified
body before work starts.

## 1. Assumed role and failure condition

| Use of NAVERA's output | Worst failure condition (see SAFETY_ANALYSIS.md) | Likely software level |
|---|---|---|
| Advisory only: operator display, GPS cross-check alarm, recording | Minor (crew workload) | **DAL D** |
| Substitute GPS to an autopilot that keeps its own EKF, failsafes and a GNSS primary; degraded positions **not** forwarded (the shipped default) | Major (loss of navigation → autopilot failsafe; a missed slow spoof) | **DAL C** |
| Sole position source in GNSS-denied flight (`forward_degraded=true`) over populated areas | Hazardous (a wrong trusted position leaves the corridor) | DAL B — not a realistic near-term target; restrict the operation instead |

The recommended near-term target is **DAL C for the arbiter + output path** (estimator, output
policy, MAVLink/NMEA encoding, GPS driver) with the vision / celestial localizers treated as
**untrusted sources monitored by that DAL C path** (a run-time-assurance pattern: ASTM F3269
style), and DAL D for the operator tools. This is the architecture the code already has: every
non-GNSS position is DEGRADED, carries its own sigma, is not forwarded by default, and is bounded
by `navera_output/policy.py` (NAV-SAF-07 … 10).

## 2. DO-178C / ED-12C (software)

What DAL C / D demand (DO-178C Annex A: 62 objectives at C, 26 at D):

| Area | DAL C / D demand | NAVERA today | Gap |
|---|---|---|---|
| Plans | PSAC, SDP, SVP, SCMP, SQAP; standards for requirements, design, code | CLAUDE.md (rules), git workflow, run_tests.sh | Write the five plans and three standards; agree PSAC with the authority |
| High-level requirements | complete, verifiable, traceable to system requirements | [REQUIREMENTS.md](REQUIREMENTS.md) — 63 system-level requirements with IDs | Derive HLR per software component; review records |
| Low-level requirements / design (C) | LLR + architecture, traceable HLR ↔ LLR ↔ code | docstrings and package READMEs; no LLR set | LLR for the DAL C components; design description |
| Traceability | bidirectional req ↔ code ↔ test | [TRACEABILITY.md](TRACEABILITY.md), generated (`navera_tools/trace_matrix.py`): 62 / 66 requirements traced to tests, 4 without | Trace at HLR/LLR level; close the 4; make trace links explicit in test docstrings |
| Requirements-based testing | normal + robustness tests for every HLR (C: also LLR) | 535 test units (516 test functions, 17 integration / SITL scripts, 2 deployment checks); robustness tests exist (spoof, NaN, future stamps) | Test procedures and results records per release; tests written from requirements, not code |
| Structural coverage | C: statement coverage; D: none | not measured | Run coverage (pytest-cov) on the DAL C components; analyse dead / deactivated code |
| Configuration management | baselines, problem reports, change control | git, branches, ENGINEERING_BACKLOG, problems log | Formal baselines per release; problem-report process with status; build reproducibility (pinned wheels) |
| Quality assurance | independent SQA records | none | SQA role and audits |
| Previously developed / COTS software | Linux, Python 3.10, ROS 2 Humble, PyTorch, OpenCV, astropy, pymavlink | used as is | **Largest gap**: none has DO-178C data. Options: keep them out of the DAL C partition (C++ or certified-runtime rewrite of the arbiter + output), or argue service history / reverse engineering (rarely accepted for a Python interpreter or DDS) |
| Tool qualification (DO-330) | tools that replace a verification activity | trace_matrix.py, run_tests.sh, verify_units.py | TQL-5 qualification if their output is used as certification credit |
| Machine-learned components | not covered by DO-178C | DINOv2 (fallback), DISK + LightGlue, STHN | Follow EASA AI Concept Paper (Level 1 assistance / Level 2) and EUROCAE ED-324 / SAE ARP6983 (in work) — data management, learning assurance, generalisation evidence; until then keep ML outputs as monitored, untrusted sources |

## 3. DO-254 / ED-80 (hardware) and COTS processors

DO-254 targets custom complex electronic hardware (FPGA/ASIC). NAVERA uses COTS boards (Jetson
Orin Nano, BNO085, DS3231, Insta360 / thermal camera), so the applicable guidance is the COTS
route: AMC 20-152A / AC 20-152A (COTS electronic hardware) and, because the Orin is a multicore
SoC with a GPU, **AMC 20-193 (CAST-32A successor) for multicore interference**.

| Demand | NAVERA today | Gap |
|---|---|---|
| COTS component selection and usage domain, errata management | JetPack 6.2.1 pinned in docs; no errata process | Usage-domain document, errata watch, obsolescence plan |
| Multicore interference (AMC 20-193): identify interference channels, bound WCET under interference | GPU shared, CPU shared with other jobs; latency measured only with other jobs running | Partitioning (CPU affinity, memory limits), measured worst-case latency per pipeline under load |
| Environmental qualification (DO-160G) | none | Temperature, vibration, EMI, power-input tests of the box |
| Power / brown-out behaviour | not tested (H-12) | Hold-up and restart time on the vehicle supply |

## 4. ED-280 / SORA (UAS operation and safety assessment)

Under JARUS SORA (2.0 / 2.5) NAVERA is a **mitigation and a design feature of the UAS**, assessed
through the operational safety objectives (OSO) at the robustness the SAIL requires (EUROCAE
ED-280 is named here as the UAS safety-assessment guidance used with SORA; confirm the edition).

| OSO (SORA 2.0 numbering) | What NAVERA contributes | Evidence robustness today | Gap |
|---|---|---|---|
| #05 UAS designed considering system safety and reliability | hazard log (SAFETY_ANALYSIS.md), honest sigma, fail-to-NO_FIX | low (simulator / bench) | Quantitative FHA, flight evidence |
| #06 C3 link performance | MAVLink to the autopilot (local) | SITL | Real autopilot link tests |
| #10 / #12 safe recovery from technical issues; managing deterioration of external systems (GNSS) | the product's purpose: GNSS loss → vision; spoof refusal | SIM / BENCH / PUB | Flight demonstration; integrity figures per flight hour |
| #13 external services adequate | map, imagery licence, offline data | partial (DEP-11 licence open) | Data-quality process for the map (treat as navigation data, DO-200B / ED-76A style) |
| #18 / #19 protection from human error | token, armed lock, settings validation, check_box | UT | Usability review of /mission, integrator checklist (EK3 parameters, H-13) |
| #24 adverse environmental conditions | night / cloud / rain conditions tested synthetically | SIM / BENCH | Real weather data; DO-160G |
| Containment (step 9) | a wrong position could defeat geofencing | — | Show that containment does not depend on NAVERA alone, or bound NAVERA's error with evidence |

Medium robustness generally needs test data and simulation; high robustness needs third-party
validation. NAVERA's evidence is at "low/medium" for SAIL I–III type operations at best, and only
with a safety pilot until flight data exist.

## 5. ISO 21448 (SOTIF) — performance limitations of perception

Automotive by origin, but the most directly applicable framework for the vision pipelines: their
hazards come from **performance limits under triggering conditions**, not from faults.

| SOTIF activity | NAVERA today | Gap |
|---|---|---|
| Specification of the intended functionality and its limits | VALIDATION_STATUS.md "Known limitations"; ODD implied (textured land, ≥ ~350 m for night, Sousse map) | Written ODD per pipeline (terrain, height, speed, light, weather, map age) checked at run time where possible |
| Identify triggering conditions | stress tests: day 18 conditions × 2 strengths (F20), night 53 conditions (`night_conditions.py`), celestial junk / clouds (F11) | Real-data triggering conditions (shake, rain on the lens, real LWIR) |
| Known unsafe scenarios → mitigations | gates, guard, re-check, sigma calibration (H-02 … H-04) | Close F16 / F20 / H-01b |
| Unknown unsafe scenarios → validation target | 2599 real drone fixes (PUB), 108 bench runs | A quantitative target (e.g. wrong-and-hidden fixes per hour) and the flight hours to show it |
| Field monitoring | record_session.sh / evaluate_session.py exist | Fleet data loop and problem reporting after release |

## 6. Gap list (priority order)

1. **Certification basis** with the authority: role of NAVERA, DAL, SORA SAIL of the target operations.
2. **Flight evidence**: no FLT-level evidence for any requirement (TRACEABILITY.md).
3. **Partition the DAL C path** (arbiter + output + GPS driver) from Python/ROS/ML, or plan its re-implementation.
4. **Plans and standards** (PSAC, SDP, SVP, SCMP, SQAP; requirements / design / code standards).
5. **LLR, structural coverage, independent reviews** for the DAL C path.
6. **ML assurance** route (EASA AI guidance) for the localizers, or keep them monitored and untrusted.
7. **Multicore / GPU interference and WCET** (AMC 20-193), memory and thermal limits (H-11).
8. **Map as navigation data**: quality, date, licence (H-05, DEP-11).
9. **Environmental qualification** of the box (DO-160G) and power behaviour.
10. **Tool qualification** of the verification scripts if their results are claimed.
