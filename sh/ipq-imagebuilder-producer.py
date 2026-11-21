#!/usr/bin/env python3
"""Seal and validate the shared IPQ standalone ImageBuilder producer bundle."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REQUIRED_PROFILES = ("glinet_gl-axt1800", "jdcloud_re-cs-02")
REQUIRED_FLAGS = {
    "CONFIG_IB": "y",
    "CONFIG_IB_STANDALONE": "y",
    "CONFIG_USE_APK": "y",
}
MANIFEST_NAME = "provenance.json"
CHECKSUMS_NAME = "SHA256SUMS"
IMAGE_CONTRACT_PATH = Path(__file__).with_name("ipq-image-contract.json")
PACKAGE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._-]*\Z")


class ProducerError(ValueError):
    """Raised when a producer bundle is incomplete or cannot be audited."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ProducerError(f"bundle path escapes root: {path}") from exc
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not relative or any(part in ("", ".", "..") for part in pure.parts):
        raise ProducerError(f"unsafe path in bundle: {relative!r}")
    if "\n" in relative or "\r" in relative:
        raise ProducerError(f"unsafe path in bundle: {relative!r}")
    return relative


def _bundle_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root.resolve())
            except (OSError, ValueError) as exc:
                raise ProducerError(f"symlink escapes bundle or is broken: {path}") from exc
            if resolved.is_dir():
                continue
            if not resolved.is_file():
                raise ProducerError(
                    f"symlink target is not a regular file or directory: {path}"
                )
        elif path.is_dir():
            continue
        elif not path.is_file():
            raise ProducerError(f"unsupported filesystem entry in bundle: {path}")
        _relative_path(root, path)
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _file_records(root: Path, exclude: Iterable[str] = ()) -> List[Dict[str, object]]:
    excluded = set(exclude)
    records = []
    for path in _bundle_files(root):
        relative = _relative_path(root, path)
        if relative in excluded:
            continue
        records.append(
            {"path": relative, "sha256": _sha256(path), "size": path.stat().st_size}
        )
    return records


def _parse_config(path: Path) -> Dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.fullmatch(r"(CONFIG_[A-Za-z0-9_.+-]+)=(.*)", line)
        if match:
            values[match.group(1)] = match.group(2).strip('"')
    return values


def _image_contract() -> Mapping[str, object]:
    try:
        document = json.loads(IMAGE_CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProducerError(f"cannot read IPQ image contract: {exc}") from exc
    profiles = document.get("profiles") if isinstance(document, dict) else None
    if not isinstance(profiles, dict):
        raise ProducerError("IPQ image contract has no profiles object")
    return profiles


def _package_names(packageinfo: Path) -> set[str]:
    return set(
        re.findall(
            r"^Package:\s*([A-Za-z0-9][A-Za-z0-9+._-]*)\s*$",
            packageinfo.read_text(encoding="utf-8", errors="replace"),
            re.M,
        )
    )


def _apk_versions(
    apk_root: Path, package_names: set[str], architecture: str
) -> Dict[str, set[str]]:
    """Return package versions available for target-ABI or architecture-independent APKs."""
    versions: Dict[str, set[str]] = {}
    if not architecture:
        raise ProducerError("ImageBuilder config has no CONFIG_TARGET_ARCH_PACKAGES")
    architectures = (architecture, "all", "noarch")
    for path in apk_root.rglob("*.apk"):
        if not path.is_file() or path.stat().st_size == 0:
            continue
        filename = path.name[:-4]
        for package_arch in architectures:
            suffix = "_" + package_arch
            if not filename.endswith(suffix):
                continue
            package_version = filename[: -len(suffix)]
            separators = [
                index for index, char in enumerate(package_version) if char == "_"
            ]
            for index in reversed(separators):
                name = package_version[:index]
                version = package_version[index + 1 :]
                if name in package_names and version:
                    versions.setdefault(name, set()).add(version)
                    break
            break
    return versions


def _package_tokens(
    value: object,
    package_names: set[str],
    context: str,
    *,
    ignore_missing: bool = False,
) -> List[str]:
    """Validate package selectors, optionally skipping unavailable defaults."""
    if isinstance(value, str):
        tokens = value.split()
    elif isinstance(value, list):
        tokens = [str(token).strip() for token in value]
    else:
        raise ProducerError(f"{context} must be a package list")
    normalized = set()
    for token in tokens:
        if not token:
            continue
        name = token[1:] if token.startswith("-") else token
        if not PACKAGE_NAME_RE.fullmatch(name):
            raise ProducerError(f"invalid package selector in {context}: {token!r}")
        if name not in package_names:
            if ignore_missing:
                continue
            raise ProducerError(
                f"package selector {token!r} in {context} is not in package metadata"
            )
        normalized.add(("-" if token.startswith("-") else "") + name)
    return sorted(normalized)


def _parse_package_manifest(path: Path) -> Dict[str, str]:
    if not path.is_file() or not path.stat().st_size:
        raise ProducerError(f"producer device manifest is missing or empty: {path}")
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
            raise ProducerError(f"invalid package manifest line in {path}: {line!r}")
        if not PACKAGE_NAME_RE.fullmatch(name) or not version:
            raise ProducerError(f"invalid package record in {path}: {line!r}")
        previous = packages.get(name)
        if previous is not None and previous != version:
            raise ProducerError(
                f"producer manifest contains conflicting versions for {name}: "
                f"{previous} and {version}"
            )
        packages[name] = version
    if not packages:
        raise ProducerError(f"producer device manifest contains no packages: {path}")
    return packages


def write_package_intent(
    config_path: Path,
    profiles_path: Path,
    packageinfo_path: Path,
    manifest_dir: Path,
    output_path: Path,
) -> Dict[str, object]:
    """Resolve ImageBuilder package selectors from the producer configuration.

    The producer manifests are retained as evidence and may include runtime
    dependencies outside the standalone ImageBuilder package pool. Package
    selectors are validated against package metadata and filtered by APK
    availability for the target architecture.
    """
    package_names = _package_names(packageinfo_path)
    if not package_names:
        raise ProducerError("ImageBuilder package metadata contains no packages")
    config = _parse_config(config_path)
    apk_versions = _apk_versions(
        config_path.parent,
        package_names,
        config.get("CONFIG_TARGET_ARCH_PACKAGES", ""),
    )
    profiles_document = json.loads(profiles_path.read_text(encoding="utf-8"))
    profiles = profiles_document.get("profiles") if isinstance(profiles_document, dict) else None
    if not isinstance(profiles, dict):
        raise ProducerError("ImageBuilder profiles.json has no profiles object")
    # OpenWrt's profiles.json carries target DEFAULT_PACKAGES, which can name
    # packages omitted from this ImageBuilder's package pool. Keep available
    # defaults, while explicit profile/config selectors stay strict below.
    common_default = _package_tokens(
        profiles_document.get("default_packages", []),
        package_names,
        "profiles.json:default_packages",
        ignore_missing=True,
    )
    common_default = [name for name in common_default if name in apk_versions]
    source_manifests = {}
    for profile_name in REQUIRED_PROFILES:
        matches = sorted(manifest_dir.glob(f"*-{profile_name}.manifest"))
        if len(matches) != 1:
            raise ProducerError(
                f"expected one producer manifest for {profile_name}, found {len(matches)}"
            )
        # Shared-build manifests describe the full installed firmware and may
        # include base/runtime packages that ImageBuilder cannot select.
        source_manifests[profile_name] = _parse_package_manifest(matches[0])
    common_names = {
        name
        for name in package_names
        if config.get("CONFIG_PACKAGE_" + name) == "y" and name in apk_versions
    }
    common = []
    for name in sorted(common_names):
        versions = {
            manifest[name]
            for manifest in source_manifests.values()
            if name in manifest
        }
        common.append({"name": name, "version": versions.pop() if len(versions) == 1 else "*"})

    manifest_output_dir = output_path.parent / "manifests"
    manifest_output_dir.mkdir(parents=True, exist_ok=True)
    result_profiles = {}
    for profile_name in REQUIRED_PROFILES:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            raise ProducerError(f"profile {profile_name} is missing from profiles.json")
        explicit_device = _package_tokens(
            profile.get("device_packages", []),
            package_names,
            f"profiles.json:{profile_name}:device_packages",
        )
        missing_explicit_device = sorted(
            name for name in explicit_device if name not in apk_versions
        )
        if missing_explicit_device:
            raise ProducerError(
                f"explicit device packages are absent from matching-ABI APK pool "
                f"for {profile_name}: {', '.join(missing_explicit_device)}"
            )
        defaults = set(common_default) | set(explicit_device)
        selector = config.get(
            "CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_" + profile_name,
            "",
        )
        configured = _package_tokens(
            selector, package_names, f"CONFIG_TARGET_DEVICE_PACKAGES_{profile_name}"
        )
        excluded = {token[1:] for token in configured if token.startswith("-")}
        explicit_configured = {
            token for token in configured if not token.startswith("-")
        }
        missing_configured = sorted(
            name for name in explicit_configured if name not in apk_versions
        )
        if missing_configured:
            raise ProducerError(
                f"explicit configured packages are absent from matching-ABI APK pool "
                f"for {profile_name}: {', '.join(missing_configured)}"
            )
        desired_names = (
            common_names
            | explicit_configured
            | defaults
        ) - excluded
        manifest = source_manifests[profile_name]
        desired = {name: manifest.get(name, "*") for name in desired_names}
        manifest_path = next(manifest_dir.glob(f"*-{profile_name}.manifest"))
        shutil.copy2(
            manifest_path, manifest_output_dir / f"{profile_name}.manifest"
        )
        result_profiles[profile_name] = {
            "packages": [
                {"name": name, "version": desired[name]}
                for name in sorted(set(desired) - common_names)
            ],
            "expected": [
                {"name": name, "version": desired[name]}
                for name in sorted(desired)
            ],
            "excluded": sorted(excluded),
        }
    document = {"schema": 1, "common": common, "profiles": result_profiles}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


def _parse_sha256sums(path: Path) -> Dict[str, str]:
    if not path.is_file():
        raise ProducerError(f"producer source checksum file is missing: {path}")
    result = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        name = parts[1].lstrip("*").removeprefix("./")
        result[Path(name).name] = parts[0].lower()
    return result


def stage_recovery_images(source_dir: Path, bundle_root: Path) -> Dict[str, object]:
    """Copy fixed recovery images from this producer after checking its source sums."""
    source_dir = source_dir.resolve()
    bundle_root = bundle_root.resolve()
    source_sums = _parse_sha256sums(source_dir / "sha256sums")
    recovery = {}
    for profile_name, profile_contract in _image_contract().items():
        if profile_name not in REQUIRED_PROFILES:
            continue
        files = {}
        for image_name in profile_contract.get("producer_fallback", []):
            source = source_dir / image_name
            if not source.is_file() or source.stat().st_size == 0:
                raise ProducerError(
                    f"producer output for {profile_name} is missing recovery image {image_name}"
                )
            digest = _sha256(source)
            if source_sums.get(image_name) != digest:
                raise ProducerError(
                    f"producer checksum does not match recovery image {image_name}"
                )
            relative = f"recovery/{profile_name}/{image_name}"
            destination = bundle_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files[image_name] = {"path": relative, "sha256": digest}
        recovery[profile_name] = files
    path = bundle_root / "recovery/images.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recovery, indent=2, sort_keys=True) + "\n")
    return recovery


def _kernel_vermagic(path: Path) -> str:
    match = re.search(
        r"^\s*LINUX_VERMAGIC\s*:?=\s*([^\s#]+)",
        path.read_text(encoding="utf-8", errors="replace"),
        re.M,
    )
    return match.group(1) if match else ""


def _tree_revision(path: Path) -> str:
    """Return the Git revision, or a stable tree digest for a copied custom tree."""
    try:
        top_level = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if Path(top_level).resolve() == path.resolve():
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    digest = hashlib.sha256()
    if not path.is_dir():
        raise ProducerError(f"cannot fingerprint missing source directory: {path}")
    for child in sorted(path.rglob("*"), key=lambda p: p.relative_to(path).as_posix()):
        if ".git" in child.relative_to(path).parts or child.is_dir():
            continue
        if child.is_symlink():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(os.readlink(child).encode("utf-8"))
            digest.update(b"\0")
        elif child.is_file():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(bytes.fromhex(_sha256(child)))
    return "tree-sha256:" + digest.hexdigest()


def _revision_map(directory: Path) -> Dict[str, str]:
    if not directory.is_dir():
        return {}
    result = {}
    for child in sorted(directory.iterdir(), key=lambda p: p.name):
        if child.is_dir():
            result[child.name] = _tree_revision(child)
    return result


def collect_provenance(
    bundle_root: Path,
    source_root: Path,
    target: str,
    architecture: str,
    builder_revision: Optional[str] = None,
) -> Dict[str, object]:
    ib = bundle_root / "imagebuilder"
    config_path = ib / ".config"
    kernel_mk = ib / "include/kernel.mk"
    if not config_path.is_file() or not kernel_mk.is_file():
        raise ProducerError("ImageBuilder .config or include/kernel.mk is missing")
    config = _parse_config(config_path)
    flags = {name: config.get(name, "unset") for name in REQUIRED_FLAGS}
    flags["CONFIG_SIGNATURE_CHECK"] = config.get("CONFIG_SIGNATURE_CHECK", "unset")
    flags["CONFIG_SIGNED_PACKAGES"] = config.get("CONFIG_SIGNED_PACKAGES", "unset")
    kernel_vermagic = _kernel_vermagic(kernel_mk)
    if not kernel_vermagic or kernel_vermagic == "unknown":
        raise ProducerError("ImageBuilder kernel vermagic is missing or unknown")

    try:
        source_revision = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProducerError(f"cannot resolve source revision in {source_root}") from exc

    return {
        "contract": "ipq-imagebuilder-producer-v1",
        "source_revision": source_revision,
        "builder_revision": builder_revision or os.environ.get("GITHUB_SHA", "unknown"),
        "feeds": _revision_map(source_root / "feeds"),
        "custom_revisions": _revision_map(source_root / "package/custom"),
        "target": target,
        "architecture": architecture,
        "kernel_vermagic": kernel_vermagic,
        "package_manager": "apk",
        "build_flags": flags,
    }


def write_manifest(bundle_root: Path, provenance: Mapping[str, object]) -> None:
    root = bundle_root.resolve()
    if not root.is_dir():
        raise ProducerError(f"bundle directory does not exist: {root}")
    payload_records = _file_records(root, exclude=(MANIFEST_NAME, CHECKSUMS_NAME))
    document = dict(provenance)
    document["files"] = payload_records
    manifest = root / MANIFEST_NAME
    manifest.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = []
    for path in _bundle_files(root):
        relative = _relative_path(root, path)
        if relative == CHECKSUMS_NAME:
            continue
        lines.append(f"{_sha256(path)}  {relative}")
    (root / CHECKSUMS_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_host_tools(bundle_root: Path) -> List[str]:
    """Drop host staging symlinks that are not self-contained inside the bundle.

    OpenWrt ImageBuilders stage tools and library directories as symlinks either
    into the build machine's toolchain or to targets that do not exist after the
    archive is repacked.  These cannot be reproduced by the consumer, so remove
    them before sealing.  Symlinks that resolve inside the bundle are preserved.
    """
    root = bundle_root.resolve()
    host_root = root / "imagebuilder" / "staging_dir" / "host"
    if not host_root.is_dir():
        return []
    removed: List[str] = []
    for directory, directory_names, file_names in os.walk(host_root, followlinks=False):
        paths = [Path(directory) / name for name in (*directory_names, *file_names)]
        for path in sorted(paths, key=lambda item: item.relative_to(host_root).as_posix()):
            if not path.is_symlink():
                continue
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                removed.append(path.relative_to(host_root).as_posix())
                path.unlink()
    return removed


def _require_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.is_file() or path.stat().st_size == 0:
        raise ProducerError(f"required producer input is missing or empty: {relative}")
    return path


def _verify_hashes(root: Path) -> Mapping[str, str]:
    checksums_path = _require_file(root, CHECKSUMS_NAME)
    listed: Dict[str, str] = {}
    for line_number, line in enumerate(
        checksums_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ProducerError(f"malformed hash manifest line {line_number}")
        digest, raw_path = match.groups()
        relative = PurePosixPath(raw_path)
        if (
            relative.is_absolute()
            or any(part in ("", ".", "..") for part in relative.parts)
            or "\n" in raw_path
            or "\r" in raw_path
        ):
            raise ProducerError(f"unsafe path in hash manifest: {raw_path!r}")
        if raw_path in listed:
            raise ProducerError(f"duplicate path in hash manifest: {raw_path}")
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            raise ProducerError(f"hash manifest references missing file: {raw_path}")
        if _sha256(path) != digest:
            raise ProducerError(f"hash mismatch: {raw_path}")
        listed[raw_path] = digest

    expected = {
        _relative_path(root, path)
        for path in _bundle_files(root)
        if _relative_path(root, path) != CHECKSUMS_NAME
    }
    if set(listed) != expected:
        missing = sorted(expected - set(listed))
        extra = sorted(set(listed) - expected)
        raise ProducerError(
            f"hash manifest does not cover bundle files (missing={missing}, extra={extra})"
        )
    return listed


def _check_repository_config(path: Path) -> None:
    if not path.is_file():
        return
    for line_number, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if path.name == "repositories.conf":
            match = re.match(r"^src(?:/gz)?\s+\S+\s+(\S+)", line)
            if not match:
                continue
            location = match.group(1)
        else:
            location = line
        if not location.startswith("file:"):
            raise ProducerError(
                f"remote repository dependency in {path}:{line_number}: {location}"
            )


def validate_bundle(bundle_root: Path) -> Dict[str, object]:
    root = bundle_root.resolve()
    _require_file(root, "imagebuilder.tar.zst")
    ib = root / "imagebuilder"
    for relative in (
        "Makefile",
        ".config",
        ".targetinfo",
        ".packageinfo",
        "profiles.json",
        "include/kernel.mk",
        "packages/packages.adb",
    ):
        _require_file(ib, relative)

    for relative in (
        "metadata/.config",
        "metadata/source.config",
        "metadata/targetinfo",
        "metadata/packageinfo",
        "metadata/profiles.json",
        "metadata/package-intent.json",
        *(f"metadata/manifests/{profile}.manifest" for profile in REQUIRED_PROFILES),
        "recovery/images.json",
    ):
        _require_file(root, relative)
    config = _parse_config(ib / ".config")
    source_config = _parse_config(root / "metadata/source.config")
    for name, expected in REQUIRED_FLAGS.items():
        if config.get(name) != expected:
            raise ProducerError(
                f"ImageBuilder config requires {name}={expected}; "
                f"found {config.get(name, 'unset')}"
            )
        if source_config.get(name) != expected:
            raise ProducerError(
                f"producer source config requires {name}={expected}; "
                f"found {source_config.get(name, 'unset')}"
            )
    for symbol in (
        "CONFIG_TARGET_BOARD",
        "CONFIG_TARGET_SUBTARGET",
        "CONFIG_TARGET_ARCH_PACKAGES",
    ):
        if config.get(symbol) != source_config.get(symbol):
            raise ProducerError(f"source and ImageBuilder configs disagree on {symbol}")
    metadata_pairs = (
        ("metadata/.config", "imagebuilder/.config"),
        ("metadata/targetinfo", "imagebuilder/.targetinfo"),
        ("metadata/packageinfo", "imagebuilder/.packageinfo"),
        ("metadata/profiles.json", "imagebuilder/profiles.json"),
    )
    for metadata_path, imagebuilder_path in metadata_pairs:
        if (root / metadata_path).read_bytes() != (root / imagebuilder_path).read_bytes():
            raise ProducerError(f"metadata copy does not match ImageBuilder: {metadata_path}")

    profiles_doc = json.loads((ib / "profiles.json").read_text(encoding="utf-8"))
    profiles = profiles_doc.get("profiles")
    if not isinstance(profiles, dict):
        raise ProducerError("profiles.json has no profiles object")
    missing_profiles = [name for name in REQUIRED_PROFILES if name not in profiles]
    if missing_profiles:
        raise ProducerError(
            "ImageBuilder profiles are missing: " + ", ".join(missing_profiles)
        )
    for profile_name in REQUIRED_PROFILES:
        profile = profiles[profile_name]
        images = profile.get("images") if isinstance(profile, dict) else None
        if not isinstance(images, (list, dict)) or not images:
            raise ProducerError(f"profile {profile_name} has no image metadata")

    if not (ib / "target/linux/qualcommax").is_dir():
        raise ProducerError("ImageBuilder target/linux/qualcommax input is missing")
    if not (ib / "target/linux/generic").is_dir():
        raise ProducerError("ImageBuilder target/linux/generic input is missing")
    kernel_configs = list(ib.glob("**/linux-*/.config"))
    if not kernel_configs:
        raise ProducerError("ImageBuilder kernel .config input is missing")
    dts_files = [
        path
        for path in ib.glob("**/arch/arm64/boot/dts/**/*")
        if path.is_file() and path.stat().st_size
    ]
    if not dts_files:
        raise ProducerError("ImageBuilder arm64 DTS inputs are missing")
    host_tools = list((ib / "staging_dir/host/bin").glob("*"))
    if not any(path.is_file() and path.stat().st_size for path in host_tools):
        raise ProducerError("ImageBuilder staging_dir/host/bin inputs are missing")

    apks = [
        path for path in ib.rglob("*.apk") if path.is_file() and path.stat().st_size
    ]
    if not apks:
        raise ProducerError("ImageBuilder APK package pool is empty")
    package_names = _package_names(ib / ".packageinfo")
    arch = config.get("CONFIG_TARGET_ARCH_PACKAGES", "")
    apk_versions: Dict[str, set[str]] = {}
    for package_name in package_names:
        for path in apks:
            prefix = package_name + "_"
            if not path.name.startswith(prefix) or not path.name.endswith(".apk"):
                continue
            for package_arch in (arch, "all", "noarch"):
                suffix = "_" + package_arch + ".apk"
                if path.name.endswith(suffix):
                    version = path.name[len(prefix) : -len(suffix)]
                    if version:
                        apk_versions.setdefault(package_name, set()).add(version)
    kmods = [path for path in apks if path.name.startswith("kmod-")]
    if not kmods:
        raise ProducerError("ImageBuilder package pool contains no kmod APKs")
    intent = json.loads(
        (root / "metadata/package-intent.json").read_text(encoding="utf-8")
    )
    if not isinstance(intent, dict) or intent.get("schema") != 1:
        raise ProducerError("package-intent.json has an unsupported schema")
    common = intent.get("common")
    if not isinstance(common, list):
        raise ProducerError("package-intent.json has no common package list")
    intent_profiles = intent.get("profiles")
    if not isinstance(intent_profiles, dict):
        raise ProducerError("package-intent.json has no profiles object")
    common_by_name = {}
    for record in common:
        if (
            not isinstance(record, dict)
            or record.get("name") not in package_names
            or not isinstance(record.get("version"), str)
        ):
            raise ProducerError("package-intent common contains an invalid package record")
        common_by_name[record["name"]] = record["version"]
    for profile_name in REQUIRED_PROFILES:
        profile = profiles[profile_name]
        if not isinstance(profile, dict):
            raise ProducerError(f"profile {profile_name} is invalid")
        if not isinstance(profile.get("device_packages"), list):
            raise ProducerError(f"profile {profile_name} has no device_packages metadata")
        profile_intent = intent_profiles.get(profile_name)
        if not isinstance(profile_intent, dict):
            raise ProducerError(f"package-intent is missing profile {profile_name}")
        expected = profile_intent.get("expected")
        if not isinstance(expected, list):
            raise ProducerError(f"package-intent:{profile_name} has no expected package list")
        expected_by_name = {}
        for record in expected:
            if (
                not isinstance(record, dict)
                or record.get("name") not in package_names
                or not isinstance(record.get("version"), str)
            ):
                raise ProducerError(
                    f"package-intent:{profile_name} contains an invalid package record"
                )
            expected_by_name[record["name"]] = record["version"]
        source_manifest = root / f"metadata/manifests/{profile_name}.manifest"
        if any(
            expected_by_name.get(name) not in (version, "*") and version != "*"
            for name, version in common_by_name.items()
        ):
            raise ProducerError(
                f"package-intent common package versions disagree for {profile_name}"
            )
        excluded = profile_intent.get("excluded")
        if not isinstance(excluded, list) or any(
            not isinstance(name, str) or name not in package_names for name in excluded
        ):
            raise ProducerError(f"package-intent:{profile_name} has invalid exclusions")
        missing = sorted(
            name
            for name, version in expected_by_name.items()
            if (
                version != "*" and version not in apk_versions.get(name, set())
            ) or (version == "*" and not apk_versions.get(name))
        )
        if missing:
            raise ProducerError(
                f"producer manifest packages are absent from matching-ABI APK pool "
                f"for {profile_name}: {', '.join(missing)}"
            )
    recovery = json.loads((root / "recovery/images.json").read_text(encoding="utf-8"))
    contract = _image_contract()
    for profile_name in REQUIRED_PROFILES:
        profile_recovery = recovery.get(profile_name) if isinstance(recovery, dict) else None
        if not isinstance(profile_recovery, dict):
            raise ProducerError(f"producer recovery metadata is missing {profile_name}")
        for image_name in contract[profile_name].get("producer_fallback", []):
            record = profile_recovery.get(image_name)
            expected_path = f"recovery/{profile_name}/{image_name}"
            if not isinstance(record, dict) or record.get("path") != expected_path:
                raise ProducerError(
                    f"producer recovery image is missing or cross-device for {profile_name}: {image_name}"
                )
            image_path = root / expected_path
            if (
                not image_path.is_file()
                or image_path.stat().st_size == 0
                or record.get("sha256") != _sha256(image_path)
            ):
                raise ProducerError(
                    f"producer recovery image checksum failed for {profile_name}: {image_name}"
                )
    indexes = [
        path
        for path in ib.rglob("packages.adb")
        if path.is_file() and path.stat().st_size
    ]
    if not indexes:
        raise ProducerError("ImageBuilder APK repository index is missing or empty")

    signing_enabled = config.get("CONFIG_SIGNATURE_CHECK") == "y"
    keys_dir = ib / "keys"
    public_keys = []
    if keys_dir.is_dir():
        for key in keys_dir.rglob("*"):
            if not key.is_file() or not key.stat().st_size:
                continue
            content = key.read_bytes()[:4096]
            if b"PRIVATE KEY" in content or re.search(
                r"(?:private|secret)", key.name, re.I
            ):
                raise ProducerError(f"private key must not be included: {key.relative_to(ib)}")
            if key.suffix.lower() in (".pem", ".pub") or "public" in key.name.lower():
                public_keys.append(key)
    if signing_enabled and not public_keys:
        raise ProducerError("signature checking is enabled but no public verification key exists")

    for config_path in ib.rglob("repositories"):
        _check_repository_config(config_path)
    for config_path in ib.rglob("repositories.conf"):
        _check_repository_config(config_path)

    provenance_path = _require_file(root, MANIFEST_NAME)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for field in (
        "source_revision",
        "builder_revision",
        "feeds",
        "custom_revisions",
        "target",
        "architecture",
        "kernel_vermagic",
        "package_manager",
        "build_flags",
        "files",
    ):
        if field not in provenance or provenance[field] in ("", None):
            raise ProducerError(f"provenance is missing required field: {field}")
    if provenance["package_manager"] != "apk":
        raise ProducerError("provenance package_manager must be apk")
    expected_target = f"{config.get('CONFIG_TARGET_BOARD', '')}/{config.get('CONFIG_TARGET_SUBTARGET', '')}"
    if provenance["target"] != expected_target:
        raise ProducerError(
            f"provenance target {provenance['target']!r} does not match .config {expected_target!r}"
        )
    if provenance["architecture"] != config.get("CONFIG_TARGET_ARCH_PACKAGES"):
        raise ProducerError("provenance architecture does not match ImageBuilder .config")
    if provenance["kernel_vermagic"] != _kernel_vermagic(ib / "include/kernel.mk"):
        raise ProducerError("provenance kernel_vermagic does not match ImageBuilder metadata")
    for field in ("source_revision", "builder_revision"):
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", str(provenance[field])):
            raise ProducerError(f"provenance {field} must be a full Git commit hash")
    if not isinstance(provenance["feeds"], dict) or not provenance["feeds"]:
        raise ProducerError("provenance feeds must contain feed revisions")
    if not isinstance(provenance["custom_revisions"], dict) or not provenance["custom_revisions"]:
        raise ProducerError("provenance custom_revisions must contain custom revisions")
    for field in ("feeds", "custom_revisions"):
        for name, revision in provenance[field].items():
            if not name or not isinstance(revision, str) or not revision:
                raise ProducerError(f"provenance {field} contains an empty revision")
    if not isinstance(provenance["build_flags"], dict):
        raise ProducerError("provenance build_flags must be an object")
    for name, expected in REQUIRED_FLAGS.items():
        if provenance["build_flags"].get(name) != expected:
            raise ProducerError(f"provenance build flags require {name}={expected}")
    checksums = _verify_hashes(root)
    current_payload = [
        {
            "path": relative,
            "sha256": digest,
            "size": (root / relative).stat().st_size,
        }
        for relative, digest in sorted(checksums.items())
        if relative != MANIFEST_NAME
    ]
    if provenance["files"] != current_payload:
        raise ProducerError("provenance payload hash list does not match bundle files")

    return {
        "profiles": list(REQUIRED_PROFILES),
        "apk_count": len(apks),
        "kmod_count": len(kmods),
        "index_count": len(indexes),
        "signature_keys": [str(path.relative_to(ib)) for path in public_keys],
        "hashed_file_count": len(checksums),
        "source_revision": provenance["source_revision"],
        "target": provenance["target"],
        "architecture": provenance["architecture"],
    }


def _argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    seal = sub.add_parser("seal", help="collect provenance and seal a staged bundle")
    seal.add_argument("--bundle-root", required=True, type=Path)
    seal.add_argument("--source-root", required=True, type=Path)
    seal.add_argument("--target", required=True)
    seal.add_argument("--architecture", required=True)
    seal.add_argument("--builder-revision")
    validate = sub.add_parser("validate", help="validate a sealed producer bundle")
    validate.add_argument("--bundle-root", required=True, type=Path)
    intent = sub.add_parser(
        "package-intent",
        help="write resolved package selections for the ImageBuilder consumer",
    )
    intent.add_argument("--config", required=True, type=Path)
    intent.add_argument("--profiles", required=True, type=Path)
    intent.add_argument("--packageinfo", required=True, type=Path)
    intent.add_argument("--manifest-dir", required=True, type=Path)
    intent.add_argument("--out", required=True, type=Path)
    recovery = sub.add_parser(
        "stage-recovery",
        help="stage profile-scoped recovery images after validating source checksums",
    )
    recovery.add_argument("--source-dir", required=True, type=Path)
    recovery.add_argument("--bundle-root", required=True, type=Path)
    normalize = sub.add_parser(
        "normalize-host-tools",
        help="drop host-tool symlinks that cannot be reproduced by the consumer",
    )
    normalize.add_argument("--bundle-root", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _argparse().parse_args(argv)
    try:
        if args.command == "seal":
            provenance = collect_provenance(
                args.bundle_root.resolve(),
                args.source_root.resolve(),
                args.target,
                args.architecture,
                args.builder_revision,
            )
            write_manifest(args.bundle_root, provenance)
            print(
                json.dumps(
                    {
                        "manifest": str(args.bundle_root / MANIFEST_NAME),
                        "checksums": str(args.bundle_root / CHECKSUMS_NAME),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "normalize-host-tools":
            print(
                json.dumps(
                    {"removed": normalize_host_tools(args.bundle_root.resolve())},
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "package-intent":
            intent = write_package_intent(
                args.config,
                args.profiles,
                args.packageinfo,
                args.manifest_dir,
                args.out,
            )
            print(json.dumps(intent, indent=2, sort_keys=True))
            return 0
        if args.command == "stage-recovery":
            recovery = stage_recovery_images(args.source_dir, args.bundle_root)
            print(json.dumps(recovery, indent=2, sort_keys=True))
            return 0
        result = validate_bundle(args.bundle_root.resolve())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ipq-imagebuilder-producer: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
