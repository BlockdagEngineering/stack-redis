#!/usr/bin/env python3

import pathlib
import subprocess
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]


def parse_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


class StackDefaultsTests(unittest.TestCase):
    def test_global_scan_window_is_stack_owned(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        self.assertEqual(defaults["BDAG_GLOBAL_BLOCK_WINDOW"], "600")

        installer = (ROOT_DIR / "ops/install-dashboard.sh").read_text(encoding="utf-8")
        self.assertIn("BDAG_GLOBAL_BLOCK_WINDOW=$(stack_default BDAG_GLOBAL_BLOCK_WINDOW)", installer)
        self.assertIn("ensure_stack_default_env_value BDAG_GLOBAL_BLOCK_WINDOW", installer)

    def test_compose_tip_lag_fallback_matches_stack_default(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        expected = (
            "BDAG_GLOBAL_CACHE_MAX_TIP_LAG_BLOCKS: "
            f"${{BDAG_GLOBAL_CACHE_MAX_TIP_LAG_BLOCKS:-{defaults['BDAG_GLOBAL_CACHE_MAX_TIP_LAG_BLOCKS']}}}"
        )
        self.assertIn(expected, compose)

    def test_stale_race_reconnect_is_disabled_by_default(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertEqual(defaults["POOL_STALE_RACE_CLIENT_RECONNECT_THRESHOLD"], "0")
        self.assertIn(
            "POOL_STALE_RACE_CLIENT_RECONNECT_THRESHOLD: "
            "${POOL_STALE_RACE_CLIENT_RECONNECT_THRESHOLD:-0}",
            compose,
        )

    def test_evm_head_guard_is_advisory_by_default(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        env_example = parse_env(ROOT_DIR / ".env.example")
        portable = parse_env(ROOT_DIR / "ops/portable.env.example")
        compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertEqual(defaults["POOL_RPC_ROUTER_EVM_HEAD_GUARD_ENABLED"], "false")
        self.assertEqual(env_example["POOL_RPC_ROUTER_EVM_HEAD_GUARD_ENABLED"], "false")
        self.assertEqual(portable["POOL_RPC_ROUTER_EVM_HEAD_GUARD_ENABLED"], "false")
        self.assertIn(
            "POOL_RPC_ROUTER_EVM_HEAD_GUARD_ENABLED: "
            "${POOL_RPC_ROUTER_EVM_HEAD_GUARD_ENABLED:-false}",
            compose,
        )

    def test_pool_database_defaults_match_compose(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        env_example = parse_env(ROOT_DIR / ".env.example")
        pool_ops = (ROOT_DIR / "ops/pool_ops.py").read_text(encoding="utf-8")

        self.assertEqual(defaults["BDAG_POOL_DB_USER"], "bdag_pool")
        self.assertEqual(defaults["BDAG_POOL_DB_NAME"], "bdagpool")
        self.assertEqual(env_example["POSTGRES_USER"], defaults["BDAG_POOL_DB_USER"])
        self.assertEqual(env_example["POSTGRES_DB"], defaults["BDAG_POOL_DB_NAME"])
        self.assertIn('os.environ.get("BDAG_POOL_DB_USER", "bdag_pool")', pool_ops)
        self.assertIn('os.environ.get("BDAG_POOL_DB_NAME", "bdagpool")', pool_ops)

    def test_native_safe_mining_defaults_are_stack_owned(self) -> None:
        defaults = parse_env(ROOT_DIR / "ops/config/stack-defaults.env")
        env_example = parse_env(ROOT_DIR / ".env.example")
        compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

        expected = {
            "NODE_DATA_DIR": "./data/node",
            "POOL_ASIC_ARP_TABLE_PATH": "/host/proc/net/arp",
            "POOL_RPC_ROUTER_NODE_HEALTH_FRESH_TEMPLATE_GRACE_SECONDS": "15",
            "POOL_RPC_ROUTER_NODE_HEALTH_MIN_CONSENSUS_PEERS": "2",
            "POOL_RECENT_STALE_BLOCK_CANDIDATE_SUBMIT_GRACE_MS": "0",
            "POOL_AUTO_TUNE_BLOCK_CANDIDATE_JOB_AGE": "true",
            "POOL_AUTO_TUNE_BLOCK_CANDIDATE_MAX_AGE_MS": "8000",
            "POOL_PREEMPTIVE_BLOCK_CANDIDATE_CLEAN_REISSUE_ENABLED": "false",
            "POOL_PREEMPTIVE_BLOCK_CANDIDATE_REFRESH_DELAY_MS": "0",
            "POOL_PREEMPTIVE_BLOCK_CANDIDATE_REFRESH_INTERVAL_MS": "20",
            "POOL_PREEMPTIVE_BLOCK_CANDIDATE_REFRESH_TIMEOUT_MS": "1000",
        }
        for key, value in expected.items():
            self.assertEqual(defaults[key], value)
            self.assertEqual(env_example[key], value)
            self.assertIn(f"${{{key}:-{value}}}", compose)

    def test_stack_defaults_validator_passes(self) -> None:
        result = subprocess.run(
            ["python3", "scripts/validate-stack-defaults.py"],
            cwd=ROOT_DIR,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
