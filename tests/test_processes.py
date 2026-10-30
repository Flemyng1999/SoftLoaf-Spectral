import os
import subprocess
import sys
from spectral_app.processes import process_alive


def test_liveness_probe_does_not_signal_the_parent_or_child():
    assert process_alive(os.getpid())
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
    try:
        assert process_alive(child.pid)
        assert child.poll() is None
    finally:child.terminate();child.wait(timeout=10)
    assert not process_alive(child.pid)
