"""Shared helpers for the portfolio deploy chart repo.

This repo is the single source of truth for what is deployed where:

  environments/<env>.yaml   pins the image each environment runs
  images/<image-id>/        an immutable snapshot of a built site
  images/index.json         the registry listing every stored image
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENTS_DIR = REPO_ROOT / "environments"
IMAGES_DIR = REPO_ROOT / "images"
INDEX_PATH = IMAGES_DIR / "index.json"

ENV_KEYS = ("name", "domain", "image", "description")


def slugify(value: str, max_len: int = 40) -> str:
    """Lowercase, hyphenate, and trim a branch name for use in an image id."""
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_len].strip("-")


def make_image_id(branch: str, sha: str) -> str:
    """Deterministic image id: <branch-slug>-<short-sha>."""
    if not sha:
        raise ValueError("sha is required to build an image id")
    return f"{slugify(branch)}-{sha[:7]}"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_env_yaml(text: str) -> dict:
    """Parse an environment manifest.

    The manifests are deliberately flat `key: value` documents so they stay
    readable without pulling in a YAML dependency. Unknown keys are kept.
    """
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"not a 'key: value' line: {raw!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
    return data


def load_env(environment: str) -> dict:
    path = ENVIRONMENTS_DIR / f"{environment}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"unknown environment: {environment} ({path})")
    env = parse_env_yaml(path.read_text())
    missing = [k for k in ENV_KEYS if not env.get(k)]
    if missing:
        raise ValueError(f"{path.name} is missing required keys: {', '.join(missing)}")
    return env


def write_env(environment: str, updates: dict) -> Path:
    """Rewrite an environment manifest, preserving key order and comments."""
    path = ENVIRONMENTS_DIR / f"{environment}.yaml"
    lines = path.read_text().splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and ":" in stripped:
            key = stripped.partition(":")[0].strip()
            if key in updates:
                out.append(f"{key}: {updates[key]}")
                seen.add(key)
                continue
        out.append(raw)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}: {value}")
    path.write_text("\n".join(out) + "\n")
    return path


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"images": []}
    return json.loads(INDEX_PATH.read_text())


def save_index(index: dict) -> None:
    INDEX_PATH.write_text(json.dumps(index, indent=2, sort_keys=False) + "\n")


def find_image(index: dict, image_id: str) -> dict | None:
    for entry in index.get("images", []):
        if entry.get("id") == image_id:
            return entry
    return None


def image_dir(image_id: str) -> Path:
    return IMAGES_DIR / image_id


def list_images(index: dict, branch: str | None = None) -> list[dict]:
    entries = index.get("images", [])
    if branch:
        entries = [e for e in entries if e.get("branch") == branch]
    return sorted(entries, key=lambda e: e.get("registered_at", ""), reverse=True)
