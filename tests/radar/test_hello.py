# REQ-RAD-010
import subprocess
import sys

def test_hello():
    result = subprocess.run(
        [sys.executable, "src/radar/hello.py"],
        capture_output = True,
        text = True,
        check = True
    )
    assert result.stdout.strip() == "Hello"
