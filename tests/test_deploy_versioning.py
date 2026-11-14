"""Offline proof that consecutive release builds get distinct Docker nonces."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest


class VersionedDeployTests(unittest.TestCase):
    def test_two_identical_source_builds_use_unique_nonces_and_one_deploy_each(self):
        script = Path(__file__).resolve().parents[1] / "deploy.sh"
        self.assertTrue(script.is_file(), "Versioned deploy script must ship with releases")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "docker"
            executable.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n",
                encoding="utf-8")
            executable.chmod(0o700)
            journal = root / "calls.txt"
            env = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "FAKE_DOCKER_LOG": str(journal),
            }
            env.pop("FINANCE_BUILD_NONCE", None)
            for _ in range(2):
                result = subprocess.run(
                    ["sh", str(script)], env=env, cwd=root, text=True,
                    capture_output=True, check=False, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
            calls = journal.read_text(encoding="utf-8").splitlines()
            builds = [line for line in calls
                      if line.startswith("compose build --build-arg ")]
            startups = [line for line in calls
                        if line.startswith("compose up -d --no-build ")]
            self.assertEqual(len(builds), 2, calls)
            self.assertEqual(len(startups), 2, calls)
            nonces = []
            for line in builds:
                match = re.search(
                    r"FINANCE_BUILD_NONCE=([0-9a-f]{32}) finance-dashboard$", line)
                self.assertIsNotNone(match, line)
                nonces.append(match.group(1))
            self.assertEqual(len(set(nonces)), 2)
            self.assertTrue(all(" --wait --wait-timeout 120 finance-dashboard" in line
                                for line in startups))
            self.assertEqual(len([line for line in calls
                                  if line.startswith("compose exec -T finance-dashboard")]), 2)

    def test_deploy_refuses_reused_explicit_nonce(self):
        script = Path(__file__).resolve().parents[1] / "deploy.sh"
        with TemporaryDirectory() as temporary:
            env = {**os.environ, "FINANCE_BUILD_NONCE": "reused"}
            result = subprocess.run(
                ["sh", str(script)], env=env, cwd=temporary, text=True,
                capture_output=True, check=False, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn("unset it before deployment", result.stderr)


if __name__ == "__main__":
    unittest.main()
