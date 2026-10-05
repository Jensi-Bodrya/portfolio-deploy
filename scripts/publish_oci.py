#!/usr/bin/env python3
"""Publish a static portfolio site as an immutable OCI artifact in GHCR."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import make_image_id

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--owner", default=os.getenv("GHCR_OWNER", ""))
    args = parser.parse_args()
    token = os.getenv("GHCR_TOKEN", "")
    owner = args.owner.lower()
    if not token or not owner:
        print("ERROR: set GHCR_TOKEN and GHCR_OWNER", file=sys.stderr)
        return 2
    source = Path(args.source_dir).resolve()
    if not (source / "index.html").is_file():
        print("ERROR: source directory must contain index.html", file=sys.stderr)
        return 2
    if not shutil.which("oras"):
        print("ERROR: oras CLI is required", file=sys.stderr)
        return 2
    image_id = make_image_id(args.branch, args.sha)
    ref = f"ghcr.io/{owner}/portfolio-images:{image_id}"
    actor = os.getenv("GITHUB_ACTOR", owner)
    login = subprocess.run(["oras", "login", "ghcr.io", "-u", actor, "--password-stdin"],
                           input=token, text=True, capture_output=True)
    if login.returncode:
        print(login.stderr, file=sys.stderr)
        return login.returncode
    with tempfile.TemporaryDirectory(prefix="portfolio-oci-") as temp:
        tar_path = Path(temp) / "site.tar"
        with tarfile.open(tar_path, "w") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file(): archive.add(path, arcname=path.relative_to(source))
        command = ["oras", "push", ref,
                   f"{tar_path}:application/vnd.jensi.portfolio.site.v1.tar",
                   "--annotation", f"org.opencontainers.image.title={image_id}",
                   "--annotation", "org.opencontainers.image.source=https://github.com/Jensi-Bodrya/portfolio",
                   "--annotation", f"org.opencontainers.image.revision={args.sha}",
                   "--annotation", f"org.opencontainers.image.ref.name={args.branch}"]
        pushed = subprocess.run(command, text=True, capture_output=True)
        if pushed.returncode:
            print(pushed.stdout); print(pushed.stderr, file=sys.stderr)
            return pushed.returncode
    print(json.dumps({"image_id": image_id, "oci_ref": ref,
                      "branch": args.branch, "sha": args.sha}))
    if pushed.stdout: print(pushed.stdout)
    return 0

if __name__ == "__main__": raise SystemExit(main())
