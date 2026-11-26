"""Host-independent regression coverage for the single Laskin deployment."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "preflight-laskin-ai26.sh"


class LaskinConsolidationTest(unittest.TestCase):
    def run_preflight(self, host: str, port: str, verified: str, legacy: bool = False, listener: bool = False):
        """Use fake local services and a disposable checkout, never touch a host."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "deploy").mkdir()
            (root / "deploy" / "preflight-checkout-ai26.py").write_text(
                "# synthetic checkout verification stub\n", encoding="utf-8"
            )
            bin_dir = root / ".venv" / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").symlink_to(sys.executable)
            scripts = {
                "ss": (
                    '#!/bin/sh\n'
                    + ("echo 'LISTEN 0 32 127.0.0.1:8502 0.0.0.0:*'\n" if listener else "")
                ),
                "git": ('#!/bin/sh\ncase "$*" in *--show-toplevel*) pwd;; *"rev-parse HEAD"*) printf "%040d\\n" 1;; *status*) exit 0;; esac\n'),
                "tailscale": '#!/bin/sh\necho 100.64.0.1\n',
                "laclaugpt-visualize": '#!/bin/sh\nexit 0\n',
                "systemctl": (
                    '#!/bin/sh\n'
                    'case "$*" in *is-enabled*laclaugpt-ai26-dashboard.service) exit '
                    + ("0" if legacy else "1") + ';; esac\nexit 1\n'
                ),
            }
            for name, content in scripts.items():
                executable = bin_dir / name
                executable.write_text(content, encoding="utf-8")
                executable.chmod(0o755)
            private_env = root / "synthetic.env"
            private_env.write_text(
                "LACLAUGPT_VIS_PROJECT_ID=ai26\n"
                "LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical\n"
                "LACLAUGPT_VIS_MACHINE=linux-server\n"
                "LACLAUGPT_VIS_EXECUTION=web-service\n"
                f"LACLAUGPT_VIS_SERVER_HOST={host}\n"
                f"LACLAUGPT_VIS_SERVER_PORT={port}\n"
                f"LACLAUGPT_VIS_NETWORK_ACCESS_VERIFIED={verified}\n"
                f"LACLAUGPT_VIS_RELEASE_SHA={1:040d}\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                PATH=f"{bin_dir}:{env['PATH']}",
                LACLAUGPT_VIS_REPO_ROOT=str(root),
                LACLAUGPT_VIS_ENV_FILE=str(private_env),
                LACLAUGPT_VIS_VENV=str(root / ".venv"),
            )
            return subprocess.run(
                ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
            )

    def test_private_port_with_verified_acl(self):
        result = self.run_preflight("100.64.0.1", "8504", "1")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_retired_listener_blocks_start(self):
        result = self.run_preflight("100.64.0.1", "8504", "1", listener=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("listener still occupies", result.stderr)

    def test_invalid_settings_fail_closed(self):
        cases = [
            ("100.64.0.1", "8501", "1", False, "port 8504"),
            ("0.0.0.0", "8504", "1", False, "private IPv4"),
            ("203.0.113.1", "8504", "1", False, "private IPv4"),
            ("100.64.0.1", "8504", "0", False, "network ACLs"),
            ("100.64.0.1", "8504", "1", True, "active or enabled"),
        ]
        for host, port, verified, legacy, message in cases:
            with self.subTest(host=host, port=port, verified=verified, legacy=legacy):
                result = self.run_preflight(host, port, verified, legacy)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
