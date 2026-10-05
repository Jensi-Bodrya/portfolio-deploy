#!/usr/bin/env python3
"""Register a built site as an immutable image in this chart repo.

This is the "push" half of the pipeline. The application repo builds its site,
then calls this to store the result under images/<image-id>/. From that point
on the image is addressable by id and any environment can be pointed at it.

Usage:
    python3 scripts/register_image.py \
        --source-dir /path/to/build \
        --branch feat/nav-spacing \
        --sha 20e2e6a94656dd56940fd7764f50c0d7ea255276 \
        [--source-repo Jensi-Bodrya/portfolio] \
        [--force]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import (  # noqa: E402
    IMAGES_DIR,
    find_image,
    image_dir,
    load_index,
    make_image_id,
    save_index,
    utcnow,
)

REQUIRED_PAYLOAD = "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, help="directory containing the built site")
    parser.add_argument("--branch", required=True, help="source branch")
    parser.add_argument("--sha", required=True, help="source commit sha")
    parser.add_argument("--source-repo", default="Jensi-Bodrya/portfolio")
    parser.add_argument("--force", action="store_true", help="overwrite an existing image id")
    args = parser.parse_args()

    source = Path(args.source_dir).resolve()
    if not source.is_dir():
        print(f"ERROR: source dir not found: {source}", file=sys.stderr)
        return 1
    if not (source / REQUIRED_PAYLOAD).exists():
        print(f"ERROR: {REQUIRED_PAYLOAD} missing from {source}", file=sys.stderr)
        return 1

    image_id = make_image_id(args.branch, args.sha)
    dest = image_dir(image_id)
    payload_dir = dest / "site"

    index = load_index()
    existing = find_image(index, image_id)
    if existing and not args.force:
        print(f"image {image_id} already registered "
              f"(branch={existing['branch']} sha={existing['sha']}) — nothing to do")
        return 0

    if dest.exists():
        shutil.rmtree(dest)
    payload_dir.mkdir(parents=True)

    copied: list[str] = []
    for item in sorted(source.iterdir()):
        if item.is_file():
            shutil.copy2(item, payload_dir / item.name)
            copied.append(item.name)
        elif item.is_dir():
            shutil.copytree(item, payload_dir / item.name)
            copied.append(item.name + "/")

    manifest = {
        "id": image_id,
        "branch": args.branch,
        "sha": args.sha,
        "source_repo": args.source_repo,
        "registered_at": utcnow(),
        "files": copied,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    index.setdefault("images", [])
    if existing:
        index["images"] = [e for e in index["images"] if e.get("id") != image_id]
    index["images"].append(manifest)
    save_index(index)

    print(f"registered image: {image_id}")
    print(f"  branch: {args.branch}")
    print(f"  sha:    {args.sha}")
    print(f"  path:   images/{image_id}")
    print(f"  files:  {', '.join(copied)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
