#!/usr/bin/env python3
"""Create one active SEO production-run manifest without overwriting evidence."""

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path


def manifest_path(value: str | None) -> Path:
    return Path(value or os.environ.get("SEO_RUN_MANIFEST") or ".seo-run/active.json")


def new_manifest(route: str) -> dict[str, object]:
    return {
        "schema": "seo-run-manifest/v1",
        "run_id": uuid.uuid4().hex,
        "route": route,
        "status": "IN_PROGRESS",
        "stages": {},
        "candidates": {},
    }


def create_manifest(path: Path, route: str) -> dict[str, object]:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = new_manifest(route)
    temporary_path: Path | None = None
    file_descriptor = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            file_descriptor = None
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, path)
        return manifest
    except FileExistsError as exc:
        raise RuntimeError(
            f"SEO run manifest already exists at {path}; refusing to replace an existing run, including IN_PROGRESS"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", choices=("traditional", "emerging"), required=True)
    parser.add_argument("--manifest", help="manifest path; defaults to SEO_RUN_MANIFEST or .seo-run/active.json")
    args = parser.parse_args()
    try:
        manifest = create_manifest(manifest_path(args.manifest), args.route)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
