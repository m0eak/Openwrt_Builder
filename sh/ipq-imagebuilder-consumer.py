#!/usr/bin/env python3
"""Validate files produced by an IPQ standalone ImageBuilder consumer run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, List, Mapping, Sequence


PROFILES = ("glinet_gl-axt1800", "jdcloud_re-cs-02")
IMAGEBUILDER_BIN_DIR = Path("bin/targets/qualcommax/ipq60xx")


class ConsumerError(ValueError):
    """Raised when an ImageBuilder consumer output is incomplete."""


def _profile_images(profile: Mapping[str, object], profile_name: str) -> List[str]:
    raw_images = profile.get("images")
    if isinstance(raw_images, dict):
        image_records = [{"name": name} for name in raw_images]
    elif isinstance(raw_images, list):
        image_records = [
            item if isinstance(item, dict) else {"name": str(item)}
            for item in raw_images
        ]
    else:
        raise ConsumerError(f"profile {profile_name} has no image metadata")

    names = []
    for record in image_records:
        name = str(record.get("name", ""))
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or len(path.parts) != 1
            or any(part in ("", ".", "..") for part in path.parts)
        ):
            raise ConsumerError(
                f"profile {profile_name} has an unsafe image name: {name!r}"
            )
        names.append(name)
    if not names:
        raise ConsumerError(f"profile {profile_name} lists no images")
    return names


def _load_profiles(
    workdir: Path, output_dir: Path
) -> Mapping[str, object]:
    output_profiles = output_dir / "profiles.json"
    root_profiles = workdir / "profiles.json"
    profiles_paths = [
        path
        for path in (output_profiles, root_profiles)
        if path.is_file() and path.stat().st_size > 0
    ]
    if not profiles_paths:
        raise ConsumerError(
            "ImageBuilder profiles.json is missing or empty from both "
            f"{IMAGEBUILDER_BIN_DIR} and the ImageBuilder root"
        )
    profiles_path = profiles_paths[0]
    try:
        document = json.loads(profiles_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConsumerError(f"invalid ImageBuilder profiles.json: {exc}") from exc
    profiles = document.get("profiles") if isinstance(document, dict) else None
    if not isinstance(profiles, dict):
        raise ConsumerError("ImageBuilder profiles.json has no profiles object")
    return profiles


def verify_outputs(workdir: Path, profile_name: str) -> Dict[str, object]:
    """Verify the manifest and all images declared for one profile."""
    if profile_name not in PROFILES:
        raise ConsumerError(f"unsupported consumer profile: {profile_name}")
    root = workdir.resolve()
    if not root.is_dir():
        raise ConsumerError(f"ImageBuilder workdir does not exist: {root}")
    output_dir = root / IMAGEBUILDER_BIN_DIR
    if not output_dir.is_dir():
        raise ConsumerError(
            f"ImageBuilder output directory is missing: {IMAGEBUILDER_BIN_DIR}"
        )

    profiles = _load_profiles(root, output_dir)
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise ConsumerError(f"profile {profile_name} is missing from profiles.json")
    image_names = _profile_images(profile, profile_name)

    image_prefix = profile.get("image_prefix")
    if image_prefix is not None:
        prefix_path = PurePosixPath(str(image_prefix))
        if (
            not str(image_prefix)
            or prefix_path.is_absolute()
            or len(prefix_path.parts) != 1
        ):
            raise ConsumerError(
                f"profile {profile_name} has an unsafe image_prefix: {image_prefix!r}"
            )
        manifest_candidates = [output_dir / f"{image_prefix}.manifest"]
    else:
        manifest_candidates = sorted(output_dir.glob(f"*-{profile_name}.manifest"))
    existing_manifests = [
        path
        for path in manifest_candidates
        if path.is_file() and path.stat().st_size > 0
    ]
    if len(existing_manifests) != 1:
        raise ConsumerError(
            f"profile {profile_name} must produce exactly one non-empty manifest; "
            f"found {len(existing_manifests)}"
        )

    missing_images = []
    for image_name in image_names:
        image_path = output_dir / image_name
        if not image_path.is_file() or image_path.stat().st_size == 0:
            missing_images.append(image_name)
    if missing_images:
        raise ConsumerError(
            f"profile {profile_name} is missing image output: "
            + ", ".join(missing_images)
        )

    return {
        "profile": profile_name,
        "manifest": existing_manifests[0].relative_to(root).as_posix(),
        "images": image_names,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--workdir", type=Path, required=True)
    verify.add_argument("--profile", required=True)
    args = parser.parse_args(argv)

    try:
        result = verify_outputs(args.workdir, args.profile)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ipq-imagebuilder-consumer: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
