# Redis Dashboard Deploy Difficulties - 2026-06-19

Context: local source deployment of `redis-dash-0-0-1` on Ubuntu 26.04 with
chain data from `/home/jeremy/Downloads/bdag-latest-snapshot.tar.gz`.

## Difficulties

- Docker was not installed. This host needed `docker.io`, `docker-compose-v2`,
  and `docker-buildx`; sudo first required a validated passwordless sudoers
  drop-in.
- The local file was named `.tar.gz` but was Zstandard-compressed raw chain
  data, not a `.bdsnap`. It contained `BdagChain/`, `bdageth/`, metadata, and a
  peerstore backup.
- The release installer only handled `.bdsnap` staging. It did not provide an
  explicit raw datadir archive path.
- A clean Docker host did not have `postgres:15-bookworm`; starting with
  `--pull never` failed until `pool-db` was pulled explicitly.
- Installer/docs referred to `postgres node dashboard`, but the compose service
  name is `pool-db`; `postgres` is only the container name.
- `pool` uses host networking, so compose-service DNS names such as
  `pool-db` and `node` do not resolve there. The pool must use
  `127.0.0.1` for Postgres and node RPC.
- `dashboard` runs on the compose bridge while `node` and `pool` use host
  networking. It needs `host.docker.internal:host-gateway` and host-facing
  defaults for EVM RPC, pool metrics, and collector API.
- Several TCP-open peers rejected libp2p security negotiation because the stored
  peer ID was stale or the peer reset the handshake.
- The peer `/ip4/13.140.165.186/tcp/8150/p2p/16Uiu2HAm4hHD7Ht5LJrLgaKXr7YP2RzHHjrrCLNt8zv8FQ9s3gBU`
  handshook and was ahead briefly, then dropped.
- The corrected peer
  `/ip4/16.28.133.168/tcp/8151/p2p/16Uiu2HAkx4trymxQDexfzCNrtWokprH49vNg8shhEhtPMYdq2CtY`
  handshook, but it was far behind the local chain tip, so it is not a
  mining-safe sync reference.
- Enabling node mining exposed a config-file permission trap. Local `.env` and
  `node.conf` were mode `0600` owned by the host user; after the entrypoint
  dropped privileges to `bdagStack`, `blockdag-node` could not read
  `/etc/bdagStack/node.conf`, logged `permission denied`, and silently fell back
  to the default `data/mainnet` datadir. That created
  `data/node/data/mainnet` and replayed from genesis instead of using the synced
  `data/node/mainnet` snapshot.
- A release fix now prepares a `bdagStack`-owned runtime copy of `node.conf`
  before dropping privileges and rewrites `--configfile` to that copy. The
  wrong fresh replay tree was parked locally as
  `data/node/data.wrong-fresh-20260620-001923`.
- With the config readable, direct RPC returned `isCurrent=true`,
  `getBlockCount=11964435`, and pool-style `getBlockTemplate` returned a
  usable mining template. The pool then subscribed to the node
  `blockTemplate` stream and reported a healthy backend.
- The ASIC inventory rows are not proof that hardware firmware has accepted the
  Stratum config. On this host the pool showed `pool_active_connections=0` and
  `pool_connections_total=0` after restart, while all four ASIC HTTP endpoints
  were reachable. Miner-control writes remain disabled locally with
  `BDAG_MINER_CONTROL_ENABLED=0`; previous unauthenticated ASIC config writes
  returned HTTP 401, so applying/restarting ASIC firmware still requires valid
  ASIC admin credentials or an enabled authenticated control path.

## Safety Outcome

- `node`, `postgres`, `dashboard`, and `pool` were left running after direct
  native RPC reported `isCurrent=true`, at least one active mainnet peer was
  present, and `getBlockTemplate` returned a usable result.
- `pool` was listening on `192.168.1.100:3334` with fresh node work, but no
  ASICs were connected. The status page state was therefore
  `Waiting for a Miner`, not `Mining`.
- Do not interpret dashboard inventory rows with `status=configured` as active
  miner connections. Require Stratum connection/share evidence before calling
  the pool mining.

## 2026-06-20 Hardening Addendum

This setup exposed several release defects that must be prevented in source,
not worked around by an operator at install time.

### P2P Port Drift Was the Root Failure

The local runtime had `.env` and firewall expectations for P2P port `8150`, but
`node.conf` still contained `port=8154`. With host networking, the node
advertised and listened on the wrong libp2p service port. TCP probes could still
look open against some remote hosts, but libp2p security negotiation reset or
timed out because the peer address being exercised was not the durable public
service endpoint expected by the release.

Mitigations now required by source:

- `.env.example` owns `P2P_PORT=8150`.
- `docker-compose.yml` passes `P2P_PORT` into the `node` service.
- `node.conf.example` must contain `port=8150` and must not contain
  `port=8154`.
- `docker/entrypoint-nodeworker.sh` reads the mounted `node.conf` before
  dropping privileges. If the configured `port` differs from `P2P_PORT`, it
  writes a private runtime config for `bdagStack` with `port=<P2P_PORT>` and
  leaves the mounted operator file unchanged.
- `scripts/validate-release-build.sh` and
  `scripts/release_bootstrap_static_test.py` reject the old `8154` drift.

Expected first-install result: the node listens on `0.0.0.0:8150`, RPC listens
on `127.0.0.1:38131`, and no service reports or advertises `8154` unless an
operator deliberately changes both the environment and config.

### Host-Network Services Need Host-Reachable RPC URLs

`node` and `pool` use `network_mode: host`, so host-side watchdog/status code
cannot assume Compose DNS names such as `node` resolve from the host. The old
default `BDAG_NODE_RPC_URLS=node=http://node:38131` made status collection fail
or fall back to weaker signals.

Mitigations now required by source:

- `.env.example` defaults to
  `BDAG_NODE_RPC_URLS=node=http://127.0.0.1:38131`.
- `ops/pool_ops.py` maps inspected host-network containers to `127.0.0.1` when
  building host-side mining RPC URLs.
- Deployment portability tests cover both explicit loopback URLs and
  host-network service-name translation.

### Dashboard Sync Status Must Follow Native Template Health

The dashboard and status sampler must not report `synced` merely because an EVM
height check looks current or a Redis cache is stale. The native node method
`getTemplateHealth` is the authoritative mining-safety source when available.

Mitigations now required by source:

- Status is `synced` only when native template health proves chain freshness:
  `p2p_mining_fresh`, `sync_allowed`, `chain_current`, peer lead within
  tolerance, and enough fresh consensus peers. Mining safety additionally
  requires `mineable_now`, `submit_ready`, and `get_block_template_ready`.
- If native template health reports peer lead, stale P2P freshness, or
  `node_syncing`, status is `syncing` and includes the native health reason.
- Public EVM RPC hash mismatches are diagnostic only unless they show the
  explicit solo-miner divergence signature. During this incident, public EVM
  endpoints disagreed with each other at the same heights, so they cannot be
  the hard mining gate.
- Recent node import logs are not a hard sync blocker when native template
  health is P2P-fresh, sync-allowed, chain-current, and within peer-lead
  tolerance. A live node imports blocks continuously while mining.
- The pool is expected to invalidate current jobs and show zero ready miners
  while native template health is unsafe, then resume only after
  `submit_ready=true` and P2P freshness returns.

### EVM Reference Gap Must Close, Not Just Move

During catch-up, a node can keep importing blocks while still failing to gain
on the live EVM chain. Active imports are useful, but they are not sufficient
proof that the system will become mining-safe soon.

Mitigations now required by source:

- The status sampler records `ops/runtime/evm-reference-gap-watch.json` while
  local EVM is more than `BDAG_EVM_REFERENCE_GAP_STALL_MIN_LAG_BLOCKS` behind
  an independent EVM reference.
- Compose deployments run the status sampler as a low-priority ops service so
  the same mining imperative and gap watch are active even when user systemd
  timers are not installed.
- If `evm_lag_to_reference` does not improve by
  `BDAG_EVM_REFERENCE_GAP_STALL_MIN_IMPROVEMENT_BLOCKS` within
  `BDAG_EVM_REFERENCE_GAP_STALL_RESTORE_SECONDS`, the sampler starts the
  existing fail-closed chain-state self-heal path.
- Chain-state self-heal stops/parks mining work, quarantines the stale node
  data, restores from a configured trusted source or snapshot, restarts
  node/dashboard, and leaves the pool stopped until readiness gates pass.
- Local EVM sync lag is advisory when native template health and pool backend
  metrics prove mining safety (`mineable`, `submit_ready`, `p2p_mining_fresh`,
  zero peer lead). It becomes a hard blocker only when native safety is missing
  or public/reference evidence shows explicit divergence or solo-mining risk.

### Peer Lists And Peerstores Need Durable Service Endpoints

Observed high NAT ports and stale peer IDs are not durable bootstrap addresses.
Seed lists must prefer operator-supplied or live public service-port multiaddrs
with matching peer IDs. When a wrong local port or stale peerstore has been in
use, clear or move the stale peerstore before judging the new peer list.

Cold installs should use the packaged peers plus any operator-maintained stable
service peers, then verify real handshakes through `getPeerInfo`. TCP-open
alone is not proof of a usable consensus peer.

### Do Not Source Complex `.env` Files In Shell Checks

The release `.env` can contain values that are valid for Compose but unsafe to
source directly in `bash`. Operator scripts must parse the specific key they
need or use the existing Python/Compose helpers. Ad hoc `source .env` checks can
mis-execute continuation-style values and hide the real failure.

### Direct Metrics Are The Runtime Source Of Truth

Dashboard tables and Redis caches are visibility aids. They are not proof that
miners are connected or that the pool is issuing current work. The runtime
source of truth is:

- direct native RPC: `getTemplateHealth`, `getPeerInfo`, `getBlockTemplate`;
- direct pool metrics: `pool_job_health_ready_miners`,
  `pool_job_health_authorized_miners`, `pool_shares_accepted_total`, and
  `pool_blocks_found_total`;
- direct container/process state: `docker ps`, listening ports, and recent
  `pool`/`node` logs.

`backend_mineable` and `backend_submit_ready` can briefly drop to zero during
parent/template invalidation immediately after accepted blocks. Redis-dash
therefore records a per-sample `accepted_block_submissions_delta` from the live
pool metrics stream. A fresh accepted-block delta may bridge that transient only
when P2P freshness, peer lead, ready miners, and template age are also safe; it
must not be replaced with a lifetime accepted-block total.

ASIC MAC identity must not be pinned to stale IP addresses. During the live
recovery, `POOL_ASIC_MAC_OVERRIDES` still mapped a previous DHCP assignment, so
two active Stratum lanes were reported with the same MAC even though the host ARP
table had the correct current IP-to-MAC mapping. Pool releases must prefer a
complete live ARP/neighbor entry over an override and use overrides only as a
fallback when the container cannot see LAN neighbors.

During the fixed run, the pool correctly moved from zero ready miners while the
node was behind peers to four ready miners after native health returned
`submit_ready=true`.

### ASIC Pool APIs Can Wedge While Controllers Stay Alive

X100 controllers can still answer `/mcb/status` and `/mcb/setting` while the
pool/cgminer endpoint `/mcb/pools` times out or returns errors. Treating that
as "not a miner" hides a recoverable ASIC and leaves pool operators looking at
only the surviving miners.

Mitigations now required by source:

- Miner discovery keeps an ASIC visible when status/settings identify it but
  the pool API is wedged. The scan row includes `pool_api_error`, an empty
  pool list, and `active=false` instead of disappearing.
- MAC address remains the canonical ASIC identity. DHCP/IP reuse after restart
  is expected; do not key miner health, retirement, or restart decisions by IP.
- When native/pool health is good but an ASIC has controller responses and no
  pool API, restart that ASIC controller first. Do not restart node or pool for
  this symptom.
