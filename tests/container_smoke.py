"""Isolated release-image startup and recovery checks; never uses Compose data.

Run after building: python tests/container_smoke.py --image finance-dashboard:check
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


def wait_for_health(name: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = json.loads(docker("inspect", name).stdout)[0]["State"]
        if not state["Running"]:
            raise AssertionError(docker("logs", name).stderr)
        result = docker("exec", name, "python", "-c",
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=2)",
            check=False)
        if result.returncode == 0:
            return
        time.sleep(0.25)
    raise AssertionError("Isolated image did not become healthy: " + docker("logs", name).stderr)


def run(image: str) -> None:
    names: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="finance-image-smoke-") as temp:
        root = Path(temp)
        data = root / "writable"
        data.mkdir(mode=0o777)
        data.chmod(0o777)
        blocked = root / "unwritable"
        blocked.mkdir()
        sentinel = blocked / "retain-me.txt"
        sentinel.write_text("existing state must survive\n")
        blocked.chmod(0o555)

        def start(folder: Path) -> str:
            name = "finance-smoke-" + uuid4().hex[:12]
            names.add(name)
            docker("run", "-d", "--name", name, "--network", "none", "--user", "23456:23457",
                   "-e", "FINANCE_AUTO_REFRESH=0", "-e", "FINANCE_AUTO_BACKUP=1",
                   "-v", f"{folder}:/data", image)
            return name

        def execute(name: str, code: str) -> str:
            return docker("exec", name, "python", "-c", code).stdout

        try:
            name = start(data)
            wait_for_health(name)
            execute(name, "from pathlib import Path; import sqlite3; "
                "c=sqlite3.connect('/data/finance.sqlite3'); "
                "c.execute('CREATE TABLE recovery_marker (value INTEGER)'); "
                "c.execute('INSERT INTO recovery_marker VALUES (42)'); c.commit(); c.close(); "
                "Path('/data/owner-inputs.json').write_text('{\"version\":1}'); "
                "assert not Path('/data/backups').exists(); "
                "assert not Path('/data/source-policy/rate-ledger.sqlite3').exists()")
            docker("rm", "-f", name)
            names.remove(name)
            name = start(data)
            wait_for_health(name)
            execute(name, "import sqlite3; "
                "c=sqlite3.connect('/data/finance.sqlite3'); "
                "assert c.execute('SELECT value FROM recovery_marker').fetchone()[0]==42; c.close()")
            docker("exec", name, "python", "-m", "finance_dashboard", "backup", "local",
                   "--output-dir", "/data/backups")
            execute(name, "from pathlib import Path; from finance_dashboard.backup import restore_backup; "
                "m=next(Path('/data/backups').glob('finance-*Z.json')); "
                "restore_backup(m,Path('/data/restored')); "
                "assert Path('/data/restored/owner-inputs.json').read_text()=='{\"version\":1}'")
            denied = start(blocked)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                state = json.loads(docker("inspect", denied).stdout)[0]["State"]
                if not state["Running"]:
                    assert state["ExitCode"] != 0, "Unwritable storage unexpectedly started"
                    break
                time.sleep(0.25)
            else:
                raise AssertionError("Unwritable storage did not fail startup")
            assert sentinel.read_text() == "existing state must survive\n"
            assert sorted(p.name for p in blocked.iterdir()) == [sentinel.name]
            print("Passed: fresh storage, UID/GID 23456:23457, offline startup, populated recreation, "
                  "backup/restore, unwritable storage preserves existing files")
        finally:
            for name in names:
                docker("rm", "-f", name, check=False)
            # Files made by the container use its selected UID; remove through
            # an equally isolated helper to keep non-root CI cleanup possible.
            docker("run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "python",
                   "-v", f"{data}:/data", image, "-c",
                   "import pathlib,shutil; "
                   "[shutil.rmtree(p) if p.is_dir() else p.unlink() for p in pathlib.Path('/data').iterdir()]",
                   check=False)
            blocked.chmod(0o755)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    run(parser.parse_args().image)
