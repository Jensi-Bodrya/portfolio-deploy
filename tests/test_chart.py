"""Tests for the portfolio deployment chart repository.

Run: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib import load_env, make_image_id, parse_env_yaml, slugify  # noqa: E402


class TestSlugsAndImageRefs(unittest.TestCase):
    def test_branch_path_becomes_docker_safe_slug(self):
        self.assertEqual(slugify("feat/nav spacing"), "feat-nav-spacing")

    def test_slug_lowercases_and_truncates(self):
        self.assertLessEqual(len(slugify("A" * 120)), 40)
        self.assertEqual(slugify("Release/Alpha"), "release-alpha")

    def test_image_id_uses_short_sha(self):
        self.assertEqual(make_image_id("feat/nav", "abcdef123456"), "feat-nav-abcdef1")

    def test_empty_sha_fails(self):
        with self.assertRaises(ValueError):
            make_image_id("main", "")


class TestEnvironments(unittest.TestCase):
    def test_three_environment_manifests_exist(self):
        for name in ("dev", "dev-2", "prod"):
            with self.subTest(name=name):
                env = load_env(name)
                self.assertEqual(env["name"], name)
                self.assertTrue(env["domain"].endswith(".surge.sh"))
                self.assertTrue(env["image"])

    def test_domains_are_unique(self):
        domains = [load_env(n)["domain"] for n in ("dev", "dev-2", "prod")]
        self.assertEqual(len(domains), len(set(domains)))

    def test_flat_manifest_parser_comments_and_quotes(self):
        self.assertEqual(
            parse_env_yaml('# top\nname: "dev"\ndomain: example.surge.sh\n'),
            {"name": "dev", "domain": "example.surge.sh"},
        )

    def test_unknown_environment_fails(self):
        with self.assertRaises(FileNotFoundError):
            load_env("not-an-env")


class TestDeployOCI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "deploy_oci.py"), *args],
            text=True, capture_output=True, cwd=ROOT,
        )

    def test_deploy_script_exists(self):
        self.assertTrue((ROOT / "scripts" / "deploy_oci.py").is_file())

    def test_dry_run_resolves_selected_environment_and_image(self):
        result = self.run_cli(
            "--environment", "dev-2",
            "--image", "ghcr.io/jensi-bodrya/portfolio-images:feat-x-abcdef1",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("environment: dev-2", result.stdout)
        self.assertIn("jensi-bodrya-dev2.surge.sh", result.stdout)
        self.assertIn("ghcr.io/jensi-bodrya/portfolio-images:feat-x-abcdef1", result.stdout)
        self.assertIn("dry-run", result.stdout)

    def test_dry_run_does_not_need_secrets_or_oras(self):
        result = self.run_cli("--environment", "dev", "--image", "example/image:test", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_environment_fails(self):
        result = self.run_cli("--environment", "missing", "--image", "example/image:test", "--dry-run")
        self.assertNotEqual(result.returncode, 0)


class TestPublishOCI(unittest.TestCase):
    def test_missing_credentials_fail_before_network_or_publish(self):
        env = {k: v for k, v in __import__("os").environ.items() if k not in ("GHCR_TOKEN", "GHCR_OWNER")}
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "publish_oci.py"),
             "--source-dir", str(ROOT), "--branch", "feat/test", "--sha", "abc123"],
            text=True, capture_output=True, env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GHCR_TOKEN", result.stderr)


if __name__ == "__main__":
    unittest.main()
