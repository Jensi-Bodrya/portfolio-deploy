"""Tests for the portfolio deploy chart repo.

Run with:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lib import (  # noqa: E402
    find_image,
    list_images,
    load_env,
    load_index,
    make_image_id,
    parse_env_yaml,
    slugify,
)

ENVIRONMENTS = ["dev", "dev-2", "prod"]


class TestSlugify(unittest.TestCase):
    def test_slashes_become_hyphens(self):
        self.assertEqual(slugify("feat/nav-spacing"), "feat-nav-spacing")

    def test_uppercase_is_lowered(self):
        self.assertEqual(slugify("FEAT/Foo"), "feat-foo")

    def test_repeated_separators_collapse(self):
        self.assertEqual(slugify("feat//a__b"), "feat-a-b")

    def test_leading_and_trailing_separators_are_trimmed(self):
        self.assertEqual(slugify("/feat/x/"), "feat-x")

    def test_dots_and_underscores_are_replaced(self):
        self.assertEqual(slugify("release/1.2.3_rc"), "release-1-2-3-rc")

    def test_length_is_capped(self):
        self.assertLessEqual(len(slugify("x" * 200)), 40)


class TestImageId(unittest.TestCase):
    def test_combines_branch_slug_and_short_sha(self):
        self.assertEqual(
            make_image_id("main", "20e2e6a94656dd56940fd7764f50c0d7ea255276"),
            "main-20e2e6a",
        )

    def test_feature_branch_id(self):
        self.assertEqual(
            make_image_id("feat/nav-spacing", "abcdef1234567890"),
            "feat-nav-spacing-abcdef1",
        )

    def test_same_branch_same_sha_is_stable(self):
        a = make_image_id("feat/x", "aaa1111")
        b = make_image_id("feat/x", "aaa1111")
        self.assertEqual(a, b)

    def test_empty_sha_is_rejected(self):
        with self.assertRaises(ValueError):
            make_image_id("main", "")


class TestEnvManifests(unittest.TestCase):
    def test_all_expected_environments_exist(self):
        for name in ENVIRONMENTS:
            with self.subTest(environment=name):
                self.assertTrue((REPO_ROOT / "environments" / f"{name}.yaml").exists())

    def test_each_environment_has_required_keys(self):
        for name in ENVIRONMENTS:
            with self.subTest(environment=name):
                env = load_env(name)
                self.assertEqual(env["name"], name)
                self.assertTrue(env["domain"].endswith(".surge.sh"))
                self.assertTrue(env["image"])

    def test_domains_are_unique(self):
        domains = [load_env(n)["domain"] for n in ENVIRONMENTS]
        self.assertEqual(len(domains), len(set(domains)), "environments share a domain")

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            load_env("does-not-exist")

    def test_parser_ignores_comments_and_blank_lines(self):
        text = "# comment\n\nname: dev\n\ndomain: example.surge.sh\n"
        self.assertEqual(
            parse_env_yaml(text),
            {"name": "dev", "domain": "example.surge.sh"},
        )

    def test_parser_strips_surrounding_quotes(self):
        self.assertEqual(parse_env_yaml('image: "main-abc1234"'), {"image": "main-abc1234"})

    def test_parser_rejects_malformed_lines(self):
        with self.assertRaises(ValueError):
            parse_env_yaml("this is not yaml")


class TestImageRegistry(unittest.TestCase):
    def test_index_file_exists(self):
        self.assertTrue((REPO_ROOT / "images" / "index.json").exists())

    def test_index_is_valid_json_with_images_list(self):
        index = load_index()
        self.assertIn("images", index)
        self.assertIsInstance(index["images"], list)

    def test_find_image_returns_none_for_unknown_id(self):
        self.assertIsNone(find_image(load_index(), "no-such-image"))

    def test_list_images_filters_by_branch(self):
        index = {
            "images": [
                {"id": "a", "branch": "main", "registered_at": "2026-01-02T00:00:00Z"},
                {"id": "b", "branch": "feat/x", "registered_at": "2026-01-03T00:00:00Z"},
            ]
        }
        self.assertEqual([e["id"] for e in list_images(index, "main")], ["a"])

    def test_list_images_is_newest_first(self):
        index = {
            "images": [
                {"id": "old", "branch": "main", "registered_at": "2026-01-01T00:00:00Z"},
                {"id": "new", "branch": "main", "registered_at": "2026-01-05T00:00:00Z"},
            ]
        }
        self.assertEqual([e["id"] for e in list_images(index)], ["new", "old"])


class TestRegisterImageEndToEnd(unittest.TestCase):
    """Exercise register_image.py against a throwaway copy of the repo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chart-test-"))
        shutil.copytree(REPO_ROOT / "scripts", self.tmp / "scripts")
        shutil.copytree(REPO_ROOT / "environments", self.tmp / "environments")
        (self.tmp / "images").mkdir()
        (self.tmp / "images" / "index.json").write_text('{"images": []}\n')

        self.build = self.tmp / "build"
        self.build.mkdir()
        (self.build / "index.html").write_text("<html><body>hi</body></html>\n")
        (self.build / "build-meta.json").write_text('{"branch": "feat/x"}\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_register(self, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(self.tmp / "scripts" / "register_image.py"),
                "--source-dir", str(self.build),
                "--branch", "feat/x",
                "--sha", "abcdef1234567890",
                *extra,
            ],
            capture_output=True, text=True,
        )

    def test_registration_succeeds(self):
        result = self.run_register()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("feat-x-abcdef1", result.stdout)

    def test_payload_is_stored_under_the_image(self):
        self.run_register()
        payload = self.tmp / "images" / "feat-x-abcdef1" / "site"
        self.assertTrue((payload / "index.html").exists())
        self.assertTrue((payload / "build-meta.json").exists())

    def test_manifest_records_provenance(self):
        self.run_register()
        manifest = json.loads(
            (self.tmp / "images" / "feat-x-abcdef1" / "manifest.json").read_text()
        )
        self.assertEqual(manifest["branch"], "feat/x")
        self.assertEqual(manifest["sha"], "abcdef1234567890")
        self.assertEqual(manifest["id"], "feat-x-abcdef1")

    def test_index_is_updated(self):
        self.run_register()
        index = json.loads((self.tmp / "images" / "index.json").read_text())
        self.assertEqual([e["id"] for e in index["images"]], ["feat-x-abcdef1"])

    def test_reregistering_without_force_is_a_noop(self):
        self.run_register()
        result = self.run_register()
        self.assertEqual(result.returncode, 0)
        self.assertIn("already registered", result.stdout)

    def test_source_missing_index_html_fails(self):
        (self.build / "index.html").unlink()
        result = self.run_register()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index.html missing", result.stderr)


class TestDeployEnvResolution(unittest.TestCase):
    """deploy_env.py --dry-run must resolve without touching Surge."""

    def _dry_run(self, environment, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "deploy_env.py"),
                "--environment", environment,
                "--dry-run",
                *extra,
            ],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )

    def test_dry_run_reports_the_resolved_plan(self):
        result = self._dry_run("dev-2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("environment : dev-2", result.stdout)
        self.assertIn("dry run", result.stdout)

    def test_dry_run_accepts_an_image_override(self):
        result = self._dry_run("dev-2", "--image", "feat-x-abcdef1")
        # The override does not need to exist for the plan to print, but an
        # unregistered image must be rejected.
        self.assertIn("is not registered", result.stderr)

    def test_unknown_environment_fails(self):
        result = self._dry_run("nope")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
