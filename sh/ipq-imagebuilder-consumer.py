#!/usr/bin/env python3
"""Validate files produced by an IPQ standalone ImageBuilder consumer run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, List, Mapping, Sequence


PROFILES = ("glinet_gl-axt1800", "jdcloud_re-cs-02")
IMAGEBUILDER_BIN_DIR = Path("bin/targets/qualcommax/ipq60xx")
PACKAGE_NAME_RE = re.compile(r"-?[A-Za-z0-9][A-Za-z0-9+._-]*\Z")
IMAGE_CONTRACT_PATH = Path(__file__).with_name("ipq-image-contract.json")
_IMAGE_CONTRACT = json.loads(IMAGE_CONTRACT_PATH.read_text(encoding="utf-8"))["profiles"]
REQUIRED_IMAGES = {
    profile: tuple(_IMAGE_CONTRACT[profile]["required_images"]) for profile in PROFILES
}
PRODUCER_FALLBACK_IMAGES = {
    profile: tuple(_IMAGE_CONTRACT[profile]["producer_fallback"])
    for profile in PROFILES
}


class ConsumerError(ValueError):
    """Raised when an ImageBuilder consumer output is incomplete."""


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _checksum_records(path: Path) -> Dict[str, str]:
    if not path.is_file():
        raise ConsumerError(f"checksum file is missing: {path.name}")
    records = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", fields[0]):
            continue
        filename = fields[1].lstrip("*").removeprefix("./")
        basename = Path(filename).name
        if basename in records and records[basename] != fields[0].lower():
            raise ConsumerError(f"conflicting checksum entries for {basename}")
        records[basename] = fields[0].lower()
    return records


def package_arguments(package_intent_path: Path, profile_name: str) -> List[str]:
    if profile_name not in PROFILES:
        raise ConsumerError(f"unsupported consumer profile: {profile_name}")
    try:
        document = json.loads(package_intent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsumerError(f"cannot read package intent: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ConsumerError("package-intent.json has an unsupported schema")
    common = document.get("common")
    profiles = document.get("profiles")
    if not isinstance(common, list) or not isinstance(profiles, dict):
        raise ConsumerError("package-intent.json has invalid common/profile lists")
    profile_intent = profiles.get(profile_name)
    if not isinstance(profile_intent, dict):
        raise ConsumerError(f"package intent is missing profile {profile_name}")
    expected = profile_intent.get("expected")
    excluded = profile_intent.get("excluded")
    if not isinstance(expected, list) or not isinstance(excluded, list):
        raise ConsumerError(f"package intent for {profile_name} is incomplete")
    selected = set()
    for record in common + expected:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("name"), str)
            or not PACKAGE_NAME_RE.fullmatch(record["name"])
            or not isinstance(record.get("version"), str)
        ):
            raise ConsumerError(f"package intent for {profile_name} has an invalid record")
        selected.add(record["name"])
    removed = set()
    for name in excluded:
        if not isinstance(name, str) or not PACKAGE_NAME_RE.fullmatch(name):
            raise ConsumerError(f"package intent for {profile_name} has an invalid exclusion")
        removed.add(name)
    selected -= removed
    return sorted(selected) + ["-" + name for name in sorted(removed)]


def _manifest_packages(path: Path) -> Dict[str, str]:
    packages = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) == 3 and fields[1] == "-":
            name, version = fields[0], fields[2]
        elif len(fields) == 2:
            name, version = fields
        else:
            raise ConsumerError(f"invalid manifest package record: {line!r}")
        if not PACKAGE_NAME_RE.fullmatch(name) or not version:
            raise ConsumerError(f"invalid manifest package record: {line!r}")
        packages[name] = version
    return packages


def restore_recovery_images(bundle_root: Path, workdir: Path, profile_name: str) -> List[str]:
    """Restore missing fixed images from the matching producer, checking both seals."""
    if profile_name not in PROFILES:
        raise ConsumerError(f"unsupported consumer profile: {profile_name}")
    bundle = bundle_root.resolve()
    root = workdir.resolve()
    output_dir = root / IMAGEBUILDER_BIN_DIR
    recovery_manifest = bundle / "recovery/images.json"
    try:
        records = json.loads(recovery_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsumerError(f"producer recovery metadata is unavailable: {exc}") from exc
    profile_records = records.get(profile_name) if isinstance(records, dict) else None
    if not isinstance(profile_records, dict):
        raise ConsumerError(f"producer recovery image is missing for {profile_name}")
    bundle_sums = _checksum_records(bundle / "SHA256SUMS")
    restored = []
    for image_name in PRODUCER_FALLBACK_IMAGES[profile_name]:
        target = output_dir / image_name
        if target.is_file() and target.stat().st_size:
            continue
        record = profile_records.get(image_name)
        expected_path = f"recovery/{profile_name}/{image_name}"
        if not isinstance(record, dict) or record.get("path") != expected_path:
            raise ConsumerError(
                f"producer recovery image is missing or cross-device for {profile_name}: {image_name}"
            )
        source = bundle / expected_path
        digest = str(record.get("sha256", ""))
        if (
            not source.is_file()
            or not source.stat().st_size
            or _digest(source) != digest
            or bundle_sums.get(image_name) != digest
        ):
            raise ConsumerError(
                f"producer recovery image checksum failed for {profile_name}: {image_name}"
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append(image_name)

    sums_path = output_dir / "sha256sums"
    required_names = set(REQUIRED_IMAGES[profile_name])
    lines = []
    if sums_path.exists():
        lines = [
            line
            for line in sums_path.read_text(encoding="utf-8").splitlines()
            if len(line.strip().split(maxsplit=1)) != 2
            or Path(
                line.strip().split(maxsplit=1)[1].lstrip("*").removeprefix("./")
            ).name
            not in required_names
        ]
    for image_name in REQUIRED_IMAGES[profile_name]:
        image = output_dir / image_name
        if image.is_file() and image.stat().st_size:
            digest = _digest(image)
            lines.append(f"{digest}  {image_name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return restored


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


def verify_outputs(
    workdir: Path,
    profile_name: str,
    package_intent_path: Path | None = None,
) -> Dict[str, object]:
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

    missing_required = [
        name
        for name in REQUIRED_IMAGES[profile_name]
        if not (output_dir / name).is_file() or (output_dir / name).stat().st_size == 0
    ]
    if missing_required:
        raise ConsumerError(
            f"profile {profile_name} is missing required image output: "
            + ", ".join(missing_required)
        )
    sums = _checksum_records(output_dir / "sha256sums")
    for image_name in REQUIRED_IMAGES[profile_name]:
        image = output_dir / image_name
        if sums.get(image_name) != _digest(image):
            raise ConsumerError(
                f"profile {profile_name} image checksum is missing or invalid: {image_name}"
            )

    result = {
        "profile": profile_name,
        "manifest": existing_manifests[0].relative_to(root).as_posix(),
        "images": image_names,
        "required_images": list(REQUIRED_IMAGES[profile_name]),
    }
    if package_intent_path is not None:
        intent = json.loads(package_intent_path.read_text(encoding="utf-8"))
        expected = intent["profiles"][profile_name]["expected"]
        expected_packages = {record["name"]: record["version"] for record in expected}
        excluded = set(intent["profiles"][profile_name]["excluded"])
        manifest_packages = _manifest_packages(existing_manifests[0])
        missing_packages = sorted(
            name
            for name, version in expected_packages.items()
            if (
                version != "*" and manifest_packages.get(name) != version
            ) or (version == "*" and name not in manifest_packages)
        )
        present_excluded = sorted(excluded & manifest_packages)
        if missing_packages or present_excluded:
            details = []
            if missing_packages:
                details.append(
                    "missing or ABI/version-mismatched selected packages: "
                    + ", ".join(missing_packages)
                )
            if present_excluded:
                details.append("excluded packages are present: " + ", ".join(present_excluded))
            raise ConsumerError(
                f"profile {profile_name} final manifest does not match package intent: "
                + "; ".join(details)
            )
        result["verified_package_count"] = len(expected_packages)
        result["verified_exclusions"] = sorted(excluded)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--workdir", type=Path, required=True)
    verify.add_argument("--profile", required=True)
    verify.add_argument("--package-intent", type=Path)
    package_args = subparsers.add_parser(
        "package-args", help="print validated ImageBuilder PACKAGES selectors"
    )
    package_args.add_argument("--package-intent", type=Path, required=True)
    package_args.add_argument("--profile", required=True)
    restore = subparsers.add_parser(
        "restore-recovery-images",
        help="restore missing fixed firmware images from the matching producer artifact",
    )
    restore.add_argument("--bundle-root", type=Path, required=True)
    restore.add_argument("--workdir", type=Path, required=True)
    restore.add_argument("--profile", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "package-args":
            print(" ".join(package_arguments(args.package_intent, args.profile)))
            return 0
        if args.command == "restore-recovery-images":
            restored = restore_recovery_images(
                args.bundle_root, args.workdir, args.profile
            )
            print(json.dumps({"restored": restored}, indent=2))
            return 0
        result = verify_outputs(args.workdir, args.profile, args.package_intent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ipq-imagebuilder-consumer: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
