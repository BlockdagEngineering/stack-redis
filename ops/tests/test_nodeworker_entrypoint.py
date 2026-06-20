from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker" / "entrypoint-nodeworker.sh"


class NodeworkerEntrypointTest(unittest.TestCase):
    def run_entrypoint(
        self,
        extra_env: dict[str, str],
        *,
        supported_node_flags: tuple[str, ...] = ("--nofastsyncserve",),
    ) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "BDAG_ENTRYPOINT_PRINT_NODE_FLAGS": "1",
        }
        env.update(extra_env)
        with tempfile.TemporaryDirectory() as tmp:
            fake_node = Path(tmp) / "fake-node"
            fake_node.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        'if [ "${1:-}" = "--help" ]; then',
                        *[
                            f"  printf '%s\\n' {shlex.quote(flag)}"
                            for flag in supported_node_flags
                        ],
                        "  exit 0",
                        "fi",
                        "exit 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            fake_node.chmod(0o755)
            return subprocess.run(
                [
                    "bash",
                    str(ENTRYPOINT),
                    "/bin/true",
                    f"--node-binary={fake_node}",
                    f"--node-args=--datadir={tmp}",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def assert_stdout_contains(self, result: subprocess.CompletedProcess[str], needle: str) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(needle, result.stdout)

    def test_print_mode_reports_node_args_append(self) -> None:
        result = self.run_entrypoint({"NODE_ARGS_APPEND": "--miner --maxpeers=160"})

        self.assert_stdout_contains(result, "NODE_ARGS_APPEND=--miner --maxpeers=160")

    def test_print_mode_reports_empty_node_args_append(self) -> None:
        result = self.run_entrypoint({})

        self.assert_stdout_contains(result, "NODE_ARGS_APPEND=")

    def test_print_mode_does_not_emit_removed_sync_flags(self) -> None:
        result = self.run_entrypoint(
            {
                "SYNC_SOURCE_NODE": "1",
                "NODE_ARGS_APPEND": "--cache=1024",
            }
        )

        self.assert_stdout_contains(result, "NODE_ARGS_APPEND=--cache=1024")
        combined = result.stdout + result.stderr
        self.assertNotIn("FAST", combined.upper())
        self.assertEqual("", result.stderr)

    def test_node_mining_env_appends_guard_args_without_forcing_rpc_module(self) -> None:
        result = self.run_entrypoint(
            {
                "BDAG_ENABLE_NODE_MINING": "1",
                "BDAG_NODE_MINING_ARGS": (
                    "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
                ),
            }
        )

        self.assertNotIn("--fastartifactsync", result.stdout)
        self.assert_stdout_contains(result, "--miner")
        self.assert_stdout_contains(result, "--miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc")
        self.assertNotIn("--allowminingwhennearlysynced", result.stdout)
        self.assertNotIn("--allowsubmitwhennotsynced", result.stdout)

    def test_node_mining_env_allows_blockdag_and_miner_rpc_modules(self) -> None:
        result = self.run_entrypoint(
            {
                "BDAG_ENABLE_NODE_MINING": "1",
                "BDAG_NODE_MODULES": "Blockdag,miner",
                "BDAG_NODE_MINING_ARGS": (
                    "--miner --miningaddr=0xA1Ee1005c4Ff181e93e717D2C624554b66AB7DFc"
                ),
            }
        )

        self.assert_stdout_contains(result, "--modules=Blockdag")
        self.assert_stdout_contains(result, "--modules=miner")

    def test_entrypoint_prepares_runtime_config_before_privilege_drop(self) -> None:
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        prepare_index = entrypoint.index("prepare_runtime_configfile \"$@\"")
        runuser_index = entrypoint.index("exec runuser -u bdagStack -g bdagStack -- \"$@\"")

        self.assertIn("rewrite_node_args_configfile", entrypoint)
        self.assertIn("runuser -u bdagStack -g bdagStack -- test -r \"$config_file\"", entrypoint)
        self.assertIn("chown bdagStack:bdagStack \"$runtime_config\"", entrypoint)
        self.assertIn("chmod 0600 \"$runtime_config\"", entrypoint)
        self.assertLess(prepare_index, runuser_index)

    def test_runtime_config_normalizes_config_port_to_p2p_port_before_start(self) -> None:
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        prepare_body_index = entrypoint.index("prepare_runtime_configfile()")
        normalize_index = entrypoint.index(
            "normalize_runtime_config_p2p_port \"$runtime_config\" \"$configured_port\" \"$desired_port\"",
            prepare_body_index,
        )
        chown_index = entrypoint.index("chown bdagStack:bdagStack \"$runtime_config\"", prepare_body_index)
        runuser_index = entrypoint.index("exec runuser -u bdagStack -g bdagStack -- \"$@\"")

        self.assertIn("configured_p2p_port()", entrypoint)
        self.assertIn("local port=\"${P2P_PORT:-8150}\"", entrypoint)
        self.assertIn("valid_tcp_port", entrypoint)
        self.assertIn("set_config_value \"$runtime_config\" port \"$desired_port\"", entrypoint)
        self.assertIn("node config P2P port ${current_port:-<missing>} differs", entrypoint)
        self.assertIn("needs_runtime_config=1", entrypoint)
        self.assertLess(normalize_index, chown_index)
        self.assertLess(normalize_index, runuser_index)

    def test_runtime_config_copy_overrides_stale_p2p_port_without_touching_mount(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            config_file = tmp_path / "node.conf"
            runtime_dir = tmp_path / "run"
            runtime_dir.mkdir()
            runtime_config = runtime_dir / "node.conf"
            data_dir = tmp_path / "data"
            config_file.write_text(
                "\n".join(
                    [
                        "listen=0.0.0.0",
                        "port=8154",
                        "datadir=/var/lib/bdagStack/node",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (fake_bin / "id").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        'if [ "${1:-}" = "-u" ] && [ "$#" -eq 1 ]; then printf "0\\n"; exit 0; fi',
                        'if [ "${1:-}" = "-u" ]; then printf "1000\\n"; exit 0; fi',
                        'if [ "${1:-}" = "-g" ]; then printf "1000\\n"; exit 0; fi',
                        'exec /usr/bin/id "$@"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (fake_bin / "mkdir").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        'for arg in "$@"; do',
                        '  case "$arg" in',
                        "    /var/lib/bdagStack*|/var/log/bdagStack*) exit 0 ;;",
                        "  esac",
                        "done",
                        'exec /usr/bin/mkdir "$@"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (fake_bin / "chown").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            (fake_bin / "runuser").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        'while [ "$#" -gt 0 ]; do',
                        '  if [ "$1" = "--" ]; then shift; break; fi',
                        "  shift",
                        "done",
                        'if [ "${1:-}" = "test" ]; then',
                        '  [ "${FAKE_BDAGSTACK_CAN_READ_CONFIG:-0}" = "1" ]',
                        "  exit $?",
                        "fi",
                        'exec "$@"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            for tool in ("id", "mkdir", "chown", "runuser"):
                (fake_bin / tool).chmod(0o755)

            env = {
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                "BDAG_EPHEMERAL_DIR": str(runtime_dir),
                "BDAG_ENTRYPOINT_CHOWN_MODE": "never",
                "FAKE_BDAGSTACK_CAN_READ_CONFIG": "1",
                "P2P_PORT": "8150",
            }
            result = subprocess.run(
                [
                    "bash",
                    str(ENTRYPOINT),
                    "/bin/true",
                    f"--node-args=--configfile {config_file} --datadir={data_dir}",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("node config P2P port 8154 differs from P2P_PORT=8150", result.stderr)
            self.assertRegex(runtime_config.read_text(encoding="utf-8"), r"(?m)^port=8150$")
            self.assertRegex(config_file.read_text(encoding="utf-8"), r"(?m)^port=8154$")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
