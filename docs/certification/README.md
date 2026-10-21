# NAVERA — Certification dossier

Status 2026-10-21. Generated from the code and the tests where possible; every claim carries
its evidence level (A analysis · UT software test · SIM simulator/SITL · BENCH NAVERA hardware on
a bench · PUB public real data · HW hardware in role · FLT flight). **NAVERA has not flown: no
FLT evidence exists.** Measured numbers are copied from [VALIDATION_STATUS.md](../VALIDATION_STATUS.md)
and the problems log; none is improved here.

| Document | What it is | Kept current by |
|---|---|---|
| [PRODUCT_READINESS.md](PRODUCT_READINESS.md) | one page: TRL per subsystem, the evidence, what moves it up | hand |
| [REQUIREMENTS.md](REQUIREMENTS.md) | 66 system requirements (functional, performance, safety, offline, interfaces, timing, deployment) with IDs and status | **generated** from `requirements.yaml` |
| [TRACEABILITY.md](TRACEABILITY.md) | requirement → code → tests → evidence; requirements without a test; broken links | **generated** by `navera_tools/trace_matrix.py` |
| [requirements.yaml](requirements.yaml) | the source of both pages: text, code references, test patterns, evidence | hand |
| [SAFETY_ANALYSIS.md](SAFETY_ANALYSIS.md) | hazard log / FMEA: 16 hazards, detection, mitigation in code, residual risk, open items | hand |
| [STANDARDS_MAPPING.md](STANDARDS_MAPPING.md) | DO-178C / ED-12C, DO-254 + COTS / multicore, ED-280 / SORA, ISO 21448: demands and gaps | hand |
| [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) | staged deployment validation (no root) and the production install + reboot procedure | hand + `deploy/stage_check.sh` |

Regenerate after any change to the requirements or the tests (no ROS needed, a few seconds):

```bash
python3 navera_tools/trace_matrix.py --check    # writes REQUIREMENTS.md + TRACEABILITY.md; exit 1 on a broken link
```

A test joins the matrix by itself when its name or docstring matches a requirement's pattern
(see the head of `requirements.yaml`); naming tests after what they check keeps the trace current.
