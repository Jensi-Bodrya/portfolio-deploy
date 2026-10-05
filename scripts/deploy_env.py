#!/usr/bin/env python3
"""Deploy one environment from an image stored in this chart repo.

This is the "pull" half of the pipeline. Nothing deploys from application
source directly — every environment resolves to a registered image id, so what
is running in an environment is always a traceable, immutable snapshot.

Usage:
    # deploy whatever the environment is pinned to
    python3 scripts/deploy_env.py --environment dev-2

    # deploy a specific image (e.g. a feature-branch build) and pin it
    python3 scripts/deploy_env.py --environment dev-2 --image feat-nav-spacing-20e2e6a

    # preview the resolved plan without touching Surge
    python3 scripts/deploy_env.py --environment dev-2 --dry-run

Requires SURGE_LOGIN and SURGE_TOKEN in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (  # noqa: E402
    find_image,
    image_dir,
    load_env,
    load_index,
    utcnow,
    write_env,
)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)


def http_code(url: str, timeout: int = 20) -> int:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, help="environment name (dev, dev-2, prod)")
    parser.add_argument("--image", default=None, help="image id to deploy instead of the pinned one")
    parser.add_argument("--no-pin", action="store_true",
                        help="do not persist an --image override into the environment manifest")
    parser.add_argument("--dry-run", action="store_true", help="resolve and report, do not deploy")
    parser.add_argument("--skip-verify", action="store_true", help="skip the post-deploy HTTP check")
    args = parser.parse_args()

    env = load_env(args.environment)
    index = load_index()

    pinned = env["image"]
    resolved = args.image or pinned

    entry = find_image(index, resolved)
    if not entry:
        print(f"ERROR: image '{resolved}' is not registered in images/index.json", file=sys.stderr)
        known = [e["id"] for e in index.get("images", [])][-10:]
        if known:
            print(f"       recent images: {', '.join(known)}", file=sys.stderr)
        return 1

    src = image_dir(resolved) / "site"
    if args.dry_run and entry.get("placeholder"):
        print("=" * 60)
        print(f"environment : {args.environment}")
        print(f"domain      : {env['domain']}")
        print(f"pinned image: {pinned}")
        print(f"resolved    : {resolved}  (placeholder — not deployable)")
        print("dry run — placeholder registry entry; no payload to deploy")
        return 0
    if not src.is_dir():
        print(f"ERROR: image directory missing: {src}", file=sys.stderr)
        return 1

    domain = env["domain"]
    override = bool(args.image and args.image != pinned)

    print("=" * 60)
    print(f"environment : {args.environment}")
    print(f"domain      : {domain}")
    print(f"pinned image: {pinned}")
    print(f"resolved    : {resolved}" + ("  (override)" if override else "  (pinned)"))
    print(f"source      : {entry['branch']} @ {entry['sha'][:7]}")
    print(f"registered  : {entry['registered_at']}")
    print(f"payload     : {src}")
    print("=" * 60)

    if args.dry_run:
        print("dry run — nothing deployed")
        return 0

    if not os.environ.get("SURGE_TOKEN"):
        print("ERROR: SURGE_TOKEN is not set", file=sys.stderr)
        return 1

    # Surge resolves relative to the payload dir; deploy a clean copy so the
    # chart repo's own files are never uploaded.
    staging = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / f"deploy-{args.environment}"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(src, staging)

    print(f"\nDeploying images/{resolved}/site -> {domain}")
    result = run(["surge", str(staging), domain])
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print("ERROR: surge deploy failed", file=sys.stderr)
        return result.returncode

    print(result.stdout)

    if not args.skip_verify:
        url = f"https://{domain}"
        code = 0
        for attempt in range(1, 6):
            code = http_code(url)
            if code == 200:
                break
            print(f"  verify attempt {attempt}: HTTP {code} — retrying")
            time.sleep(5)
        print(f"verified {url} -> HTTP {code}")
        if code != 200:
            print("ERROR: deployed site did not come up", file=sys.stderr)
            return 1

        served = http_code(f"{url}/build-meta.json")
        if served == 200:
            print(f"  build-meta.json served (HTTP {served})")

    if override and not args.no_pin:
        write_env(args.environment, {"image": resolved})
        print(f"pinned {args.environment} -> {resolved}")

    summary = {
        "environment": args.environment,
        "domain": domain,
        "image": resolved,
        "branch": entry["branch"],
        "sha": entry["sha"],
        "deployed_at": utcnow(),
    }
    out = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "deploy-summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
