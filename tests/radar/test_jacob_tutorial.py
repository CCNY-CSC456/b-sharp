# REQ-RAD-011
import subprocess
import sys

def test_jacob_tutorial():
    result = subprocess.run(
        [sys.executable, "src/radar/jacob_tutorial.py"],
        capture_output = True,
        text = True,
        check = True
    )
    assert result.stdout.strip() == "Radar online"
