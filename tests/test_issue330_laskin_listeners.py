"""Exercise the cutover checks with synthetic ss and Tailscale output."""
import os
import subprocess
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parents[1] / "deploy" / "check-laskin-listeners.sh"
ADDRESS = "100.64.0.1"


@pytest.mark.parametrize(("mode", "endpoints", "host", "success"), [
    ("before-start", [], ADDRESS, True),
    ("before-start", ["127.0.0.1:8501"], ADDRESS, False),
    ("before-start", [], "0.0.0.0", False),
    ("serving", [ADDRESS + ":8504"], ADDRESS, True),
    ("serving", ["0.0.0.0:8504"], ADDRESS, False),
    ("serving", [ADDRESS + ":8504", "[::]:8503"], ADDRESS, False),
    ("serving", [], ADDRESS, False),
])
def test_listener_policy(tmp_path, mode, endpoints, host, success):
    for name, output in {
        "tailscale": ADDRESS,
        "ss": "\n".join(f"LISTEN 0 128 {address} *:*" for address in endpoints),
    }.items():
        fake = tmp_path / name
        fake.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n")
        fake.chmod(0o755)
    result = subprocess.run([CHECK, mode], env={
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "LACLAUGPT_VIS_SERVER_HOST": host,
        "LACLAUGPT_VIS_SERVER_PORT": "8504",
    }, check=False)
    assert (result.returncode == 0) is success
