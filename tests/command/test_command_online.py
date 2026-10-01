# REQ-COMS-003
# Requirement: requirements/command/REQ-COMS-003.md

import subprocess
import sys


def test_command_online():
    result = subprocess.run(
        [sys.executable, "src/command/command_online.py"],
        capture_output=True,
        text=True,
        check=True
    )

    assert result.stdout.strip() == "Command online."