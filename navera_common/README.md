# navera_common — shared helpers

| Module | Content |
|---|---|
| `lifecycle` | `die_with_parent()`: a node dies with its launcher (no orphans) |
| `geo` | `dead_reckon()` (refuses unknown motion), `is_finite_latlon()` |
| `prior` | `GpsPrior`: last valid GPS fix as the vision prior |
| `pairing` | `FramePairer`: image/meta pairing on the image stamp; `exposure_stamp()` |
| `health` | `FrozenSampleDetector`, `RetryTimer` for sensor drivers |
| `params` | `declare_float()`: float parameters that accept integer overrides |

Unit tests: `navera_common/test/`.
