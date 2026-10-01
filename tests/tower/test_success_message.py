# REQ-TOW-002

import subprocess
import sys

def test_success_message():
    result = subprocess.run(
        [sys.executable, "src/tower/success_message.py"],
        capture_output = True,
        text = True,
        check = True
    )

    assert result.stdout.strip() == "Tower test successful!"