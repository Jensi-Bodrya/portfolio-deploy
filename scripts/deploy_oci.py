#!/usr/bin/env python3
"""Deploy an OCI image from GHCR using the environment's chart domain.

Requires ORAS, SURGE_LOGIN, SURGE_TOKEN and GHCR_TOKEN in the environment.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import load_env, load_index, find_image, utcnow, write_env


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--environment", required=True)
    p.add_argument("--image", required=True, help="OCI image reference, e.g. ghcr.io/jensi-bodrya/portfolio-images:feat-x-abc1234")
    p.add_argument("--no-pin", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    env = load_env(a.environment)
    ref = a.image
    domain = env["domain"]
    print("=" * 60)
    print(f"environment: {a.environment}")
    print(f"domain: {domain}")
    print(f"oci image: {ref}")
    print("dry-run" if a.dry_run else "deploy")
    print("=" * 60)
    if a.dry_run:
        return 0
    if "SURGE_TOKEN" not in os.environ:
        print("ERROR: SURGE_TOKEN not set", file=sys.stderr)
        return 2
    if not os.getenv("GHCR_TOKEN"):
        print("ERROR: GHCR_TOKEN not set", file=sys.stderr)
        return 2
    if not shutil.which("oras"):
        print("ERROR: oras CLI not installed", file=sys.stderr)
        return 2
    login = subprocess.run(["oras", "login", "ghcr.io", "-u", os.getenv("GITHUB_ACTOR", "github-actions[bot]"), "--password-stdin"], input=os.environ["GHCR_TOKEN"], text=True, capture_output=True)
    if login.returncode:
        print(login.stderr, file=sys.stderr); return login.returncode
    with tempfile.TemporaryDirectory(prefix="oci-site-") as temp:
        pull = subprocess.run(["oras", "pull", "--allow-path-traversal", ref, "-o", temp], text=True, capture_output=True)
        if pull.returncode:
            print(pull.stderr, file=sys.stderr); return pull.returncode
        payloads = list(Path(temp).glob("*.tar"))
        if not payloads:
            payloads = list(Path(temp).rglob("*.tar"))
        if not payloads:
            print("ERROR: OCI image contains no site tar payload", file=sys.stderr); return 1
        import tarfile
        staging = Path(temp) / "site"
        staging.mkdir()
        with tarfile.open(payloads[0]) as tar:
            tar.extractall(staging, filter="data")
        if not (staging / "index.html").is_file():
            print("ERROR: extracted OCI image missing index.html", file=sys.stderr); return 1
        result = subprocess.run(["surge", str(staging), domain], text=True, capture_output=True)
        if result.returncode:
            print(result.stdout); print(result.stderr, file=sys.stderr); return result.returncode
        print(result.stdout)
        time.sleep(3)
        try:
            with urllib.request.urlopen("https://" + domain, timeout=20) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except Exception:
            code = 0
        print(f"verified https://{domain} -> HTTP {code}")
        if code != 200:
            return 1
    if not a.no_pin:
        env_name = a.environment
        write_env(env_name, {"image": ref})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
