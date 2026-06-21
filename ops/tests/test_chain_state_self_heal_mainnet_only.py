import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ChainStateSelfHealMainnetOnlyTest(unittest.TestCase):
    def test_self_heal_refuses_non_mainnet_network_and_pins_restore_path(self) -> None:
        script_path = ROOT / "ops" / "chain-state-self-heal.sh"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("chain-state self-heal refuses non-mainnet network", script)
        self.assertIn('NETWORK="mainnet"', script)
        self.assertIn('NODE_NETWORK_DIR="$NODE_DATA_DIR/$NETWORK"', script)
        self.assertIn("soft_evm_restore_only", script)
        self.assertIn("native_paid_safe", script)
        self.assertNotIn('${NETWORK:-mainnet}', script)
        self.assertTrue(script_path.stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
