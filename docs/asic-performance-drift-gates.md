# ASIC Performance Drift Gates

Mining optimization changes must preserve enough data to prove whether the pool is improving or drifting.

## Required signals

- Per-ASIC block-candidate attribution must be present in `block_submissions`.
- Each attributed row must include `asic_mac`, `lane_id`, `lane_identity_source`, `worker`, `job_id`, `protocol_variant`, `backend_attempted`, `pdiff`, `share_diff`, and `job_age_ms`.
- The pool must expose current ASIC performance through `/health/asic-performance`.
- The dashboard Status tab must render ASIC performance from Redis key `bdag:asic:performance`.
- Comparisons against other pools or older tuning states must use windows of at least 30 minutes unless the result is explicitly marked as a short diagnostic sample.
- Cross-pool comparisons must be normalized by active X100 count/hash power. Local pool `0x1719...e7a0` has 4 X100s; comparison pool `0xd5f8...b1f5` has 2 X100s. Treat raw local block output as needing roughly 2x `b1f5` before calling performance comparable. Use paid blocks per X100-hour for optimization decisions.

## Regression gates

- `pool` tests must verify block-submission insert columns, attribution helper behavior, and ASIC performance rollups.
- `redis-dash` tests must verify Redis/runtime ASIC merge behavior, Status row/chart data, and Status template rendering.
- `stack-redis` release readiness must fail if Postgres is missing ASIC attribution columns or lane indexes.

These gates are intended to prevent a repeat of the blind spot where aggregate pool blocks were visible but per-ASIC paid-block contribution could not be reconstructed after container rotation.
