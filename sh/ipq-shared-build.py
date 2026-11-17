#!/usr/bin/env python3
"""Shared IPQ-60xx multi-profile build helper.

This module is intentionally conservative: it runs only standard-library code,
performs strictly scoped filesystem operations, and refuses to silently merge
configurations that cannot be represented losslessly.  The single-device
configs remain the source of truth; this helper only computes a candidate
shared .config and verifies the defconfig-normalized result against the
expected explicit selections.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple


DEVICE_SPECS: Dict[str, Dict[str, str]] = {
    "AXT-1800": {
        "label": "AXT-1800",
        "config": "config/axt1800.config",
        "profile": "glinet_gl-axt1800",
        "initial_lan": "192.168.8.1",
        "artifact": "AXT-1800",
    },
    "JDC-AX6600": {
        "label": "JDC-AX6600",
        "config": "config/jdcax6600.config",
        "profile": "jdcloud_re-cs-02",
        "initial_lan": "192.168.100.1",
        "artifact": "JDC-AX6600",
    },
}

SHARED_PREFIX = "CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_"
PACKAGES_PREFIX = "CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_"


class SharedBuildError(ValueError):
    """Raised when a shared configuration cannot be built safely."""


_CONFIG_LINE_RE = re.compile(
    r"^(?P<name>CONFIG_[A-Za-z0-9_.+-]+)=(?P<value>[A-Za-z0-9_.+@/-]*)$"
)
_CONFIG_QUOTED_RE = re.compile(
    r'^(?P<name>CONFIG_[A-Za-z0-9_.+-]+)=(?P<value>"(?:[^"\\]|\\.)*")$'
)
_DISABLED_CONFIG_LINE_RE = re.compile(r"^#\s+(?P<name>CONFIG_[A-Za-z0-9_.+-]+) is not set$")
_PACKAGE_RE = re.compile(r"^CONFIG_PACKAGE_(?P<name>[A-Za-z0-9_.+-]+)$")


def _load_package_names(source_root: Optional[Path]) -> Set[str]:
    """Load authoritative package and Kconfig suboption symbol names.

    ``make prepare-tmpinfo`` must run after preparing the custom packages.
    Source-package names and guessed Makefile names are not binary metadata.
    """
    if source_root is None:
        return set()
    root = Path(source_root)
    packageinfo = root / "tmp" / ".packageinfo"
    try:
        text = packageinfo.read_text(encoding="utf-8")
    except OSError as exc:
        raise SharedBuildError(f"cannot read package metadata {packageinfo}: {exc}") from exc
    names = set(re.findall(r"^Package:\s*([^\s]+)", text, re.M))
    if not names:
        raise SharedBuildError(f"empty package metadata: {packageinfo}")
    return names


def _load_kconfig_symbol_names(source_root: Optional[Path]) -> Set[str]:
    """Load PACKAGE_* Kconfig suboption names from tmp/.packageinfo.

    These are non-installable feature symbols generated from package Config.in
    blocks, for example ``luci-app-passwall2_INCLUDE_Haproxy``. They are valid
    global Kconfig symbols but must never appear in a DEVICE_PACKAGES string.
    """
    if source_root is None:
        return set()
    root = Path(source_root)
    packageinfo = root / "tmp" / ".packageinfo"
    symbols: Set[str] = set()
    if packageinfo.is_file():
        try:
            text = packageinfo.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for m in re.finditer(r"^[ \t]*config\s+PACKAGE_([^\s]+)", text, re.M):
            symbols.add(m.group(1).strip())
    return symbols


def _parse_config(path: Path) -> Dict[str, str]:
    """Parse an OpenWrt config fragment into {name: value|''} ('' means not set)."""
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SharedBuildError(f"cannot read config {path}: {exc}") from exc
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = _CONFIG_LINE_RE.match(line)
        if m:
            out[m.group("name")] = "" if m.group("value") == "n" else m.group("value")
            continue
        m = _CONFIG_QUOTED_RE.match(line)
        if m:
            json.loads(m.group("value"))
            out[m.group("name")] = m.group("value")
            continue
        m = _DISABLED_CONFIG_LINE_RE.match(line)
        if m:
            out[m.group("name")] = ""
            continue
        if line.startswith("#"):
            continue
        raise SharedBuildError(
            f"unhandled config line in {path}:{lineno}: {raw!r}"
        )
    return out


def _lines_for_config(values: Mapping[str, str]) -> List[str]:
    lines: List[str] = []
    for name in sorted(values):
        value = values[name]
        if name.startswith(PACKAGES_PREFIX):
            encoded = value if value.startswith('"') else json.dumps(value)
            lines.append(f"{name}={encoded}")
        elif value == "":
            lines.append(f"# {name} is not set")
        elif value in ("y", "m"):
            lines.append(f"{name}={value}")
        else:
            lines.append(f"{name}={value}")
    return lines


def _merge_explicit(
    entries: Mapping[str, Mapping[str, str]],
    package_names: Set[str],
    kconfig_symbol_names: Optional[Set[str]] = None,
) -> Tuple[Dict[str, str], List[str], List[str], List[str]]:
    """Merge explicit config entries into a shared candidate config.

    Returns (merged, conflicts, package_diffs, unknown_diagnostics).  Real
    installable packages are the only ``CONFIG_PACKAGE_*`` values that may be
    demoted to 'm' when they are not requested on every device.  Any other
    config symbol (feature suboption, scalar, string) that conflicts is
    rejected rather than silently changed.
    """
    merged: Dict[str, str] = {}
    conflicts: List[str] = []
    package_diffs: List[str] = []
    unknowns: List[str] = []
    pkg_states: Dict[str, Dict[str, str]] = {}
    non_pkg_values: Dict[str, Dict[str, str]] = {}
    kconfig_symbol_names = kconfig_symbol_names or set()

    for device_name, cfg in entries.items():
        for name, value in cfg.items():
            if name.startswith(SHARED_PREFIX) or name.startswith("CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_"):
                # Single-profile selectors are input sources; this helper
                # replaces them with multi-profile selectors and drops them.
                continue
            m = _PACKAGE_RE.match(name)
            pkg_name = m.group("name") if m else None
            if pkg_name and pkg_name in package_names:
                pkg_states.setdefault(name, {})[device_name] = value
                continue
            if pkg_name and pkg_name in kconfig_symbol_names:
                # Kconfig feature symbol, e.g.
                # CONFIG_PACKAGE_luci-app-passwall2_INCLUDE_Haproxy. It stays a
                # global y/m scalar and should not enter DEVICE_PACKAGES.
                non_pkg_values.setdefault(name, {})[device_name] = value
                continue
            if pkg_name:
                # A PACKAGE_* symbol not present in authoritative metadata:
                # either real source is missing the package, metadata was not
                # refreshed, or this is an unknown feature.  Diagnose so it is
                # never silently dropped.
                unknowns.append(name)
            non_pkg_values.setdefault(name, {})[device_name] = value

    # Real packages: a package may stay y only when every device explicitly
    # requested y.  Otherwise it is compiled once as m and install/removal is
    # handled per-device via DEVICE_PACKAGES strings.
    for sym, states in sorted(pkg_states.items()):
        device_count = len(entries)
        all_y = len(states) == device_count and all(v == "y" for v in states.values())
        if all_y:
            merged[sym] = "y"
            continue
        vals = set(states.values())
        if "y" in vals:
            merged[sym] = "m"
            pkg_diffs = []
            all_devs = sorted(entries.keys())
            for dev in all_devs:
                v = states.get(dev, "")
                if dev in states and v != "y":
                    pkg_diffs.append(f"{dev}: not y")
                elif dev not in states:
                    pkg_diffs.append(f"{dev}: unset")
            package_diffs.append(f"{_PACKAGE_RE.match(sym).group('name')}: global m (not y on every device; {'; '.join(pkg_diffs)})")
            continue
        if "m" in vals:
            merged[sym] = "m"
            continue
        merged[sym] = ""

    # An absent symbol imposes no choice. Conflicting explicit values,
    # including enable versus disable, require separate build variants.
    for name, states in sorted(non_pkg_values.items()):
        set_values = sorted(set(states.values()))
        if len(set_values) == 1:
            merged[name] = set_values[0]
            continue
        # More than one distinct explicit value means the devices disagree on
        # how this shared build option should be set.
        conflicts.append(
            f"{name}: {', '.join(f'{dev}={val}' for dev, val in sorted(states.items()))}"
        )

    for name in sorted(set(unknowns)):
        m = _PACKAGE_RE.match(name)
        if m:
            unknowns_term = f"{m.group('name')}: CONFIG_PACKAGE_* not backed by package metadata"
        else:
            unknowns_term = name
        unknown_diag = f"unknown package-like config (not in tmp/.packageinfo): {unknowns_term}"
        # Keep the config line but make the fallback unambiguous in the log.
        package_diffs.append(unknown_diag)
    return merged, conflicts, package_diffs, list(set(unknowns))


_NAME_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")


def _check_device_spec(devices: Sequence[str]) -> List[Dict[str, str]]:
    specs = []
    for name in devices:
        spec = DEVICE_SPECS.get(name)
        if spec is None:
            raise SharedBuildError(f"unknown device spec {name!r}")
        if not _NAME_SAFE_RE.match(spec["profile"]):
            raise SharedBuildError(f"unsafe profile name: {spec['profile']!r}")
        specs.append(spec)
    if len(specs) != len({s["profile"] for s in specs}):
        raise SharedBuildError("duplicate profiles in device specs")
    return specs


def _add_shared_target(merged: Dict[str, str], specs: Sequence[Dict[str, str]]) -> None:
    """Add multi-profile target selectors and per-profile package strings."""
    merged["CONFIG_TARGET_qualcommax"] = "y"
    merged["CONFIG_TARGET_qualcommax_ipq60xx"] = "y"
    merged["CONFIG_TARGET_MULTI_PROFILE"] = "y"
    merged["CONFIG_TARGET_PER_DEVICE_ROOTFS"] = "y"
    for spec in specs:
        merged[SHARED_PREFIX + spec["profile"]] = "y"
        merged[PACKAGES_PREFIX + spec["profile"]] = ""


def _format_packages(names: Sequence[str]) -> str:
    return " ".join(sorted(names))


def _assign_device_packages(
    merged: Dict[str, str],
    specs: Sequence[Dict[str, str]],
    entries: Mapping[str, Mapping[str, str]],
    package_diffs: List[str],
    package_names: Optional[Set[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """Move explicit per-device package selectors into DEVICE_PACKAGES strings.

    Each rootfs starts with globally installed y packages, then applies its
    own package additions/removals. Only common packages can therefore be y;
    differences compile as m and are installed through each profile's list.

    Existing negative tokens from the source configs are preserved so that
    defaults inherited from a common target profile (for example default
    ath11k variants) can be suppressed per device.
    """
    package_names = package_names or set()
    for spec in specs:
        cfg = entries[spec["label"]]
        positives: List[str] = []
        negatives: List[str] = []
        for name, value in cfg.items():
            m = _PACKAGE_RE.match(name)
            if not m or m.group("name") not in package_names:
                continue
            pkg = m.group("name")
            if value == "y":
                positives.append(pkg)
            elif value in ("m", ""):
                # An explicit compile-only 'm' must not be written as an
                # install positive.  A source "not set" is an explicit disable
                # and becomes a per-device negative only when the source
                # fragment really requested the removal.
                if value == "":
                    negatives.append("-" + pkg)
        merged[PACKAGES_PREFIX + spec["profile"]] = _format_packages(positives + negatives)
    return merged, package_diffs


def _split_multi_target_values(merged: Dict[str, str]) -> None:
    """Drop stale single-profile choice members after adding multi-profile."""
    single = [k for k in merged if k.startswith("CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_")]
    for name in single:
        merged.pop(name, None)


def _read_source_configs(project_root: Path, specs: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    entries: Dict[str, Dict[str, str]] = {}
    for spec in specs:
        path = project_root / spec["config"]
        if not path.is_file():
            raise SharedBuildError(f"missing source config: {path}")
        entries[spec["label"]] = _parse_config(path)
    return entries


def _effective_entries(
    project_root: Path,
    specs: Sequence[Dict[str, str]],
    package_names: Set[str],
    docker: bool,
    baseline_dir: Optional[Path],
) -> Dict[str, Dict[str, str]]:
    """Use independently normalized packages, preserving raw build options.

    A package absent from a fragment can still be installed through dependencies.
    The two single-device defconfigs provide the actual installation baseline.
    """
    entries = _read_source_configs(project_root, specs)
    for spec in specs:
        cfg = entries[spec["label"]]
        if docker:
            cfg.update(_parse_config(project_root / "config/docker-ipq.config"))
        if baseline_dir is None:
            continue
        normalized = _parse_config(Path(baseline_dir) / (spec["label"] + ".config"))
        selector = "CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_" + spec["profile"]
        if normalized.get(selector) != "y" or normalized.get("CONFIG_TARGET_MULTI_PROFILE") == "y":
            raise SharedBuildError(f"invalid single-device baseline for {spec['label']}")
        for package in package_names:
            key = "CONFIG_PACKAGE_" + package
            requested = cfg.get(key)
            resolved = normalized.get(key, "")
            if requested == "y" and resolved != "y":
                raise SharedBuildError(f"{spec['label']}: baseline lost requested {package}=y")
            if requested == "m" and resolved not in ("y", "m"):
                raise SharedBuildError(f"{spec['label']}: baseline lost requested {package}=m")
            if requested == "" and resolved == "y":
                raise SharedBuildError(f"{spec['label']}: baseline enabled explicitly disabled {package}")
            if requested == "":
                continue
            if resolved in ("y", "m"):
                cfg[key] = resolved
    return entries


def _audit_merged(merged: Mapping[str, str], specs: Sequence[Dict[str, str]]) -> Tuple[List[str], List[str]]:
    """Return (errors, notes) after computing the candidate shared config."""
    errors: List[str] = []
    notes: List[str] = []
    for spec in specs:
        sel = SHARED_PREFIX + spec["profile"]
        if merged.get(sel) != "y":
            errors.append(f"missing per-device selector {sel}=y")
        if merged.get("CONFIG_TARGET_qualcommax_ipq60xx") != "y":
            errors.append("CONFIG_TARGET_qualcommax_ipq60xx=y missing")
        if merged.get("CONFIG_TARGET_MULTI_PROFILE") != "y":
            errors.append("CONFIG_TARGET_MULTI_PROFILE=y missing")
        if merged.get("CONFIG_TARGET_PER_DEVICE_ROOTFS") != "y":
            errors.append("CONFIG_TARGET_PER_DEVICE_ROOTFS=y missing")
    stale = [
        k
        for k in merged
        if re.match(r"^CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_[A-Za-z0-9_]+$", k)
        and k not in {SHARED_PREFIX + s["profile"] for s in specs}
    ]
    if stale:
        errors.append(f"stale single-profile selectors retained: {', '.join(sorted(stale))}")
    return errors, notes


def _write_candidate(project_root: Path, merged: Mapping[str, str], dst: Optional[Path] = None) -> Path:
    if dst is None:
        dst = Path(tempfile.mkdtemp(prefix="ipq-shared-")) / "candidate.config"
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(_lines_for_config(merged)) + "\n", encoding="utf-8")
    return dst


def generate_shared_config(
    project_root: Path,
    devices: Sequence[str],
    docker: bool = False,
    source_root: Optional[Path] = None,
    out: Optional[Path] = None,
    baseline_dir: Optional[Path] = None,
) -> Dict[str, object]:
    """Generate and return the shared config plus a human audit summary."""
    specs = _check_device_spec(devices)
    package_names = _load_package_names(source_root)
    kconfig_symbol_names = _load_kconfig_symbol_names(source_root)
    entries = _effective_entries(project_root, specs, package_names, docker, baseline_dir)
    package_diffs: List[str] = []
    if docker:
        package_diffs.append("docker fragment applied to each device config before merge")
    if baseline_dir is not None:
        package_diffs.append("package selections resolved against both single-device defconfigs")
    merged, conflicts, package_diffs2, unknown_package_symbols = _merge_explicit(
        entries, package_names, kconfig_symbol_names
    )
    package_diffs += package_diffs2
    if conflicts:
        raise SharedBuildError("scalar conflicts:\n  " + "\n  ".join(conflicts))
    if unknown_package_symbols:
        raise SharedBuildError(
            "unknown package-like config symbols (prepare package metadata with `make prepare-tmpinfo` first):\n  "
            + "\n  ".join(sorted(unknown_package_symbols))
        )
    _add_shared_target(merged, specs)
    _split_multi_target_values(merged)
    merged, package_diffs = _assign_device_packages(
        merged, specs, entries, package_diffs, package_names=package_names
    )

    errors, notes = _audit_merged(merged, specs)
    if errors:
        raise SharedBuildError("shared config audit failed:\n  " + "\n  ".join(errors))
    path = _write_candidate(project_root, merged, out)
    return {
        "config": str(path),
        "devices": [s["label"] for s in specs],
        "profiles": [s["profile"] for s in specs],
        "notes": package_diffs + notes,
        "scalar_conflicts": conflicts,
    }


# libwrt 25.12.6's Image/Manifest reads only TARGET_DIR_ORIG. Attach separate
# manifests to each selected device's actual rootfs target instead.
DEVICE_MANIFEST_RULE = """
  # ipq-shared: manifests from final per-device APK databases
  ifdef TARGET_PER_DEVICE_ROOTFS
    ifneq ($$(_PROFILE_SET),)
      $$(_TARGET): $$(BIN_DIR)/$$(DEVICE_IMG_PREFIX).manifest
      $$(BIN_DIR)/$$(DEVICE_IMG_PREFIX).manifest: image_prepare target-dir-$$(ROOTFS_ID/$(1))
\t$$(call apk,$$(KDIR)/target-dir-$$(ROOTFS_ID/$(1))) list --quiet --manifest --no-network --repositories-file /dev/null > $$@.packages
\ttest -s $$@.packages
\tLC_ALL=C sort $$@.packages | sed 's/ / - /' > $$@.tmp
\tmv $$@.tmp $$@
\trm -f $$@.packages
    endif
  endif
"""


def patch_manifest_rules(source_root: Path) -> None:
    """Add per-profile manifests for the supported native APK build path."""
    cfg = _parse_config(source_root / ".config")
    if any(cfg.get(key) != "y" for key in
           ("CONFIG_USE_APK", "CONFIG_TARGET_MULTI_PROFILE", "CONFIG_TARGET_PER_DEVICE_ROOTFS")):
        raise SharedBuildError("per-device manifests require the shared APK/rootfs configuration")
    path = source_root / "include/image.mk"
    text = path.read_text()
    marker = "# ipq-shared: manifests from final per-device APK databases"
    if marker in text:
        if text.count(DEVICE_MANIFEST_RULE) != 1:
            raise SharedBuildError("per-device manifest hook drifted")
        return
    anchor = "define Device/Build\n"
    if text.count(anchor) != 1:
        raise SharedBuildError("cannot locate unique Device/Build manifest hook")
    updated = text.replace(anchor, anchor + DEVICE_MANIFEST_RULE, 1)
    descriptor, temporary = tempfile.mkstemp(prefix=".image.mk.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            os.fchmod(output.fileno(), path.stat().st_mode & 0o777)
            output.write(updated)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_profiles_json(content: str) -> List[Dict[str, object]]:
    """Parse OpenWrt profiles.json and return image metadata records."""
    data = json.loads(content)
    profiles = data.get("profiles", {})
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            raise SharedBuildError("malformed profiles.json entries")
        profile["profile_id"] = profile_id
    return list(profiles.values())


def _safe_filename(name: str) -> bool:
    if not name or name in (".", ".."):
        return False
    if os.path.isabs(name) or "/" in name or "\\" in name:
        return False
    return _NAME_SAFE_RE.match(name) is not None and name != "packages.txt"


def _resolve_safe_child(base: Path, raw: str) -> Path:
    if not _safe_filename(raw):
        raise SharedBuildError(f"unsafe filename in profiles.json: {raw!r}")
    child = (base / raw)
    try:
        resolved = child.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SharedBuildError(f"missing file referenced by profiles.json: {raw!r}") from exc
    base_res = base.resolve(strict=True)
    if base_res != resolved.parent and not resolved.is_relative_to(base_res):
        raise SharedBuildError(f"path escapes base directory: {raw!r}")
    if child.is_symlink() and not resolved.is_relative_to(base_res):
        raise SharedBuildError(f"symlink escapes base directory: {raw!r}")
    return child


def _verify_image_checksum(image: Path, expected_hash: Optional[str] = None) -> str:
    import hashlib
    digest = hashlib.sha256()
    with image.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if expected_hash is not None and expected_hash.lower() != actual:
        raise SharedBuildError(
            f"sha256 mismatch for {image.name}: expected {expected_hash}, got {actual}"
        )
    return actual


def split_outputs(
    source_dir: Path,
    destination: Path,
    devices: Sequence[str],
    *,
    require_all_profiles: bool = True,
) -> Dict[str, Dict[str, List[str]]]:
    """Split a multi-profile bin/targets directory into per-device artifacts.

    The source directory must contain profiles.json plus per-profile manifest
    and image files generated by the real build.  Every profile in devices is
    required unless require_all_profiles=False.  Path names are validated and
    All retained files receive regenerated checksums after image validation.
    """
    specs = _check_device_spec(devices)
    profile_text = _resolve_safe_child(source_dir, "profiles.json").read_text(encoding="utf-8")
    profiles_doc = json.loads(profile_text)
    profiles = parse_profiles_json(profile_text)
    by_id = {p["profile_id"]: p for p in profiles}
    unknown = set(by_id) - {s["profile"] for s in specs}
    if unknown:
        raise SharedBuildError(f"unexpected profiles in build output: {', '.join(sorted(unknown))}")
    out: Dict[str, Dict[str, List[str]]] = {}

    for spec in specs:
        profile = by_id.get(spec["profile"])
        if profile is None:
            if require_all_profiles:
                raise SharedBuildError(f"missing profile {spec['profile']} in profiles.json")
            continue
        image_prefix = profile.get("image_prefix")
        if not isinstance(image_prefix, str) or not _safe_filename(image_prefix):
            raise SharedBuildError(f"missing or unsafe image_prefix for {spec['profile']}: {image_prefix!r}")
        images = profile.get("images", [])
        if isinstance(images, list):
            image_records = [
                i if isinstance(i, dict) else {"name": str(i)} for i in images
            ]
        elif isinstance(images, dict):
            image_records = [{"name": k, "sha256": v} for k, v in images.items()]
        else:
            raise SharedBuildError(f"profile {spec['profile']}: unexpected images type")
        image_names = [str(i.get("name", "")) for i in image_records]
        image_names = [n for n in image_names if n]
        if not image_names and require_all_profiles:
            raise SharedBuildError(f"profile {spec['profile']} lists no images")
        image_paths = []
        record_by_name = {str(i.get("name", "")): i for i in image_records}
        for raw in image_names:
            try:
                p = _resolve_safe_child(source_dir, raw)
            except SharedBuildError as exc:
                if require_all_profiles:
                    raise SharedBuildError(f"image problem for {spec['profile']}: {exc}") from exc
                continue
            if not raw.startswith((image_prefix + "-", image_prefix + ".")):
                raise SharedBuildError(f"image does not belong to profile {spec['profile']}: {raw}")
            expected = record_by_name.get(raw, {}).get("sha256")
            if expected is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", str(expected)):
                raise SharedBuildError(f"malformed sha256 for {raw!r}: {expected!r}")
            actual = _verify_image_checksum(p, str(expected) if expected is not None else None)
            image_paths.append(p)
            per_file = source_dir / (raw + ".sha256sum")
            if per_file.is_file():
                per_file = _resolve_safe_child(source_dir, per_file.name)
                stored = per_file.read_text(encoding="utf-8", errors="replace").strip()
                if stored.lower() != actual:
                    raise SharedBuildError(f"mismatched .sha256sum sidecar for {raw}")

        # Real OpenWrt manifest names are:
        #   <VERSION_DIST_SANITIZED>-<BOARD>-<SUBTARGET>-<profile>.manifest
        manifests = []
        if image_prefix:
            candidate = _resolve_safe_child(source_dir, f"{image_prefix}.manifest")
            manifests.append(candidate)
        if not manifests and require_all_profiles:
            raise SharedBuildError(f"missing manifest for profile {spec['profile']}")
        if len(manifests) != 1:
            raise SharedBuildError(
                f"ambiguous manifest for profile {spec['profile']}: {[str(m) for m in manifests]}"
            )

        device_dir = destination / f"firmware-{spec['artifact']}"
        if device_dir.exists():
            shutil.rmtree(device_dir)
        device_dir.mkdir(parents=True)
        copied = []
        for image in image_paths:
            shutil.copy2(image, device_dir / image.name)
            copied.append(image.name)
        for mf in manifests:
            shutil.copy2(mf, device_dir / mf.name)
            copied.append(mf.name)
        filtered_profiles = dict(profiles_doc)
        filtered_profiles["profiles"] = {
            spec["profile"]: {k: v for k, v in profile.items() if k != "profile_id"}
        }
        (device_dir / "profiles.json").write_text(json.dumps(filtered_profiles, sort_keys=True), encoding="utf-8")
        copied.append("profiles.json")
        for name in ("config.buildinfo", "feeds.buildinfo", "version.buildinfo"):
            p = source_dir / name
            if p.is_file():
                p = _resolve_safe_child(source_dir, name)
                shutil.copy2(p, device_dir / p.name)
                copied.append(p.name)
        checksums = [f"{_verify_image_checksum(device_dir / name)} *{name}" for name in sorted(copied)]
        (device_dir / "sha256sums").write_text("\n".join(checksums) + "\n", encoding="utf-8")
        copied.append("sha256sums")
        # Do not write a global packages.txt to firmware dirs; it is uploaded
        # separately from manifests.
        out[spec["artifact"]] = {
            "files": copied,
            "manifests": [m.name for m in manifests],
            "images": [i.name for i in image_paths],
        }
    return out


def audit_normalized_packages(
    project_root: Path,
    normalized_config: Path,
    devices: Optional[Sequence[str]] = None,
    source_root: Optional[Path] = None,
    docker: bool = False,
    baseline_dir: Optional[Path] = None,
) -> List[str]:
    """Audit defconfig-normalized shared config against source package intent.

    Checks:
    - required multi-profile/per-device selectors are present
    - every package required by any device is compiled y or m (not absent/disabled)
    - device-exclusive packages are not compiled globally as y
    - each device package string includes its source-install packages, includes
      its explicit negative packages, and excludes packages owned by another
      device unless present in profile defaults.
    """
    specs = _check_device_spec(devices or list(DEVICE_SPECS))
    package_names = _load_package_names(source_root)
    entries = _effective_entries(project_root, specs, package_names, docker, baseline_dir)
    try:
        norm = _parse_config(normalized_config)
    except SharedBuildError as exc:
        raise SharedBuildError(f"cannot parse normalized config: {exc}") from exc
    problems: List[str] = []
    if norm.get("CONFIG_TARGET_qualcommax_ipq60xx") != "y":
        problems.append("CONFIG_TARGET_qualcommax_ipq60xx=y missing")
    if norm.get("CONFIG_TARGET_MULTI_PROFILE") != "y":
        problems.append("CONFIG_TARGET_MULTI_PROFILE=y missing")
    if norm.get("CONFIG_TARGET_PER_DEVICE_ROOTFS") != "y":
        problems.append("CONFIG_TARGET_PER_DEVICE_ROOTFS=y missing")
    selected = {key for key, value in norm.items() if key.startswith(SHARED_PREFIX) and value == "y"}
    expected = {SHARED_PREFIX + spec["profile"] for spec in specs}
    if selected - expected:
        problems.append(f"unexpected device profiles selected: {', '.join(sorted(selected - expected))}")
    if any(key.startswith("CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_") and value == "y"
           for key, value in norm.items()):
        problems.append("old single-device selector retained")

    per_device_positives: Dict[str, Set[str]] = {s["label"]: set() for s in specs}
    per_device_negatives: Dict[str, Set[str]] = {s["label"]: set() for s in specs}
    explicit_m: Dict[str, Set[str]] = {s["label"]: set() for s in specs}
    for spec in specs:
        sel = SHARED_PREFIX + spec["profile"]
        if norm.get(sel) != "y":
            problems.append(f"missing per-device selector {sel}=y")
        for name, value in entries[spec["label"]].items():
            m = _PACKAGE_RE.match(name)
            if not m or m.group("name") not in package_names:
                continue
            pkg = m.group("name")
            if value == "y":
                per_device_positives[spec["label"]].add(pkg)
            elif value == "":
                per_device_negatives[spec["label"]].add(pkg)
            elif value == "m":
                explicit_m[spec["label"]].add(pkg)

    all_positive_names = set().union(*per_device_positives.values()) if per_device_positives else set()
    all_negative_names = set().union(*per_device_negatives.values()) if per_device_negatives else set()
    all_m_names = set().union(*explicit_m.values()) if explicit_m else set()

    # Expected global compile state:
    # - y only when every device explicitly requested y (common install)
    # - m when exclusive (one or more devices y, not all) or explicitly m
    expected_build: Dict[str, str] = {}
    for pkg in sorted(all_positive_names):
        if all(pkg in per_device_positives[spec["label"]] for spec in specs):
            expected_build[pkg] = "y"
        else:
            expected_build[pkg] = "m"
    for pkg in all_m_names:
        expected_build.setdefault(pkg, "m")

    for pkg in sorted(all_positive_names):
        sym = "CONFIG_PACKAGE_" + pkg
        norm_val = norm.get(sym)
        if norm_val not in ("y", "m"):
            problems.append(f"{pkg}: compiled flag missing/disabled in normalized config: {norm_val!r}")
        elif norm_val == "y" and expected_build.get(pkg) != "y":
            problems.append(f"{pkg}: global compiled y leaks to all devices; expected m")
    for pkg in sorted(all_negative_names - all_positive_names):
        if norm.get("CONFIG_PACKAGE_" + pkg) == "y":
            problems.append(f"{pkg}: disabled package became global y")
    for pkg in sorted(all_m_names - all_positive_names - all_negative_names):
        sym = "CONFIG_PACKAGE_" + pkg
        norm_val = norm.get(sym)
        if norm_val not in ("y", "m"):
            problems.append(f"{pkg}: explicit m missing in normalized config: {norm_val!r}")
        elif norm_val == "y":
            # Explicit compile-only m promoted to y could leak into common
            # rootfs depending on profile defaults; flag it.
            problems.append(f"{pkg}: explicit m promoted to y in normalized config")

    for spec in specs:
        tok = norm.get(PACKAGES_PREFIX + spec["profile"])
        if tok is None:
            problems.append(f"{spec['label']}: missing {PACKAGES_PREFIX + spec['profile']}")
            continue
        tokens = set((json.loads(tok) if tok.startswith('"') else tok).split())
        positive = {t for t in tokens if not t.startswith("-")}
        negative = {t[1:] for t in tokens if t.startswith("-")}
        missing_pos = per_device_positives[spec["label"]] - positive
        # Common global-y packages may be satisfied by profile defaults or the
        # global y flag, so only exclusive positive loss is fatal.
        common_y = {
            pkg for pkg in per_device_positives[spec["label"]]
            if all(pkg in per_device_positives[other["label"]] for other in specs)
            and norm.get("CONFIG_PACKAGE_" + pkg) == "y"
        }
        if missing_pos - common_y:
            problems.append(f"{spec['label']}: missing install packages in device string: {', '.join(sorted(missing_pos))}")
        missing_neg = per_device_negatives[spec["label"]] - negative
        if missing_neg:
            problems.append(f"{spec['label']}: missing explicit negative packages in device string: {', '.join(sorted(missing_neg))}")
        for other in specs:
            if other["label"] == spec["label"]:
                continue
            leaked = (per_device_positives[other["label"]] - per_device_positives[spec["label"]]) & positive
            if leaked:
                problems.append(f"{spec['label']}: contains packages owned only by {other['label']}: {', '.join(sorted(leaked))}")
        forbidden = positive & (per_device_negatives[spec["label"]] | explicit_m[spec["label"]])
        if forbidden:
            problems.append(f"{spec['label']}: unexpected installed packages: {', '.join(sorted(forbidden))}")
    if baseline_dir is not None:
        for package in package_names - all_positive_names:
            if norm.get("CONFIG_PACKAGE_" + package) == "y":
                problems.append(f"{package}: shared global y absent from both installation baselines")
    return problems


def extract_package_list(
    manifest: Path,
    packages: Optional[Path] = None,
    flavor: str = "luci-app",
) -> Path:
    """Extract a per-final-firmware package list from a manifest."""
    if not manifest.is_file():
        raise SharedBuildError(f"manifest not found: {manifest}")
    lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = []
    for line in lines:
        pkg = line.split()[0] if line.split() else ""
        if flavor and not pkg.startswith(flavor):
            continue
        selected.append(pkg)
    selected = sorted(set(selected))
    if packages is None:
        fd, tmp = tempfile.mkstemp(suffix="packages.txt")
        os.close(fd)
        packages = Path(tmp)
    packages.write_text("\n".join(selected) + ("" if not selected else "\n"), encoding="utf-8")
    return packages


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="generate shared config")
    gen.add_argument("--project-root", default=".", type=Path)
    gen.add_argument("--source-root", required=True, type=Path)
    gen.add_argument("--device", action="append", default=[], help="device label, repeatable")
    gen.add_argument("--docker", action="store_true")
    gen.add_argument("--out", type=Path)
    gen.add_argument("--baseline-dir", required=True, type=Path)
    patch = sub.add_parser("patch-manifests", help="prepare native per-device APK manifest rules")
    patch.add_argument("--source-root", required=True, type=Path)
    split = sub.add_parser("split-outputs", help="split per-device outputs")
    split.add_argument("--source-dir", required=True, type=Path)
    split.add_argument("--destination", required=True, type=Path)
    split.add_argument("--device", action="append", default=[], help="device label, repeatable")
    pkg = sub.add_parser("package-list", help="extract manifest package list")
    pkg.add_argument("--manifest", required=True, type=Path)
    pkg.add_argument("--out", required=True, type=Path)
    pkg.add_argument("--flavor", default="luci-app")
    audit = sub.add_parser("audit-normalized", help="audit explicit package intent after defconfig")
    audit.add_argument("--project-root", default=".", type=Path)
    audit.add_argument("--normalized-config", required=True, type=Path)
    audit.add_argument("--source-root", required=True, type=Path)
    audit.add_argument("--device", action="append", default=[], help="device label, repeatable")
    audit.add_argument("--docker", action="store_true", help="apply docker-ipq.config to source intents")
    audit.add_argument("--baseline-dir", required=True, type=Path)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _argparse().parse_args(argv)
    try:
        if args.command == "generate":
            project = Path(args.project_root).resolve()
            devices = args.device or list(DEVICE_SPECS)
            result = generate_shared_config(
                project,
                devices,
                docker=args.docker,
                source_root=args.source_root,
                out=args.out,
                baseline_dir=args.baseline_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "patch-manifests":
            patch_manifest_rules(Path(args.source_root).resolve())
            print("per-device manifest rules ready")
        elif args.command == "split-outputs":
            devices = args.device or list(DEVICE_SPECS)
            result = split_outputs(
                Path(args.source_dir).resolve(),
                Path(args.destination).resolve(),
                devices,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "package-list":
            p = extract_package_list(
                Path(args.manifest).resolve(),
                Path(args.out).resolve(),
                flavor=args.flavor,
            )
            print(p)
        elif args.command == "audit-normalized":
            problems = audit_normalized_packages(
                Path(args.project_root).resolve(),
                Path(args.normalized_config).resolve(),
                args.device,
                args.source_root,
                docker=args.docker,
                baseline_dir=args.baseline_dir,
            )
            for problem in problems:
                print(problem, file=sys.stderr)
            if problems:
                raise SharedBuildError(f"{len(problems)} normalized package intent problem(s)")
            print("audit-normalized: OK")
        else:
            raise SharedBuildError(f"unhandled command {args.command!r}")
        return 0
    except (SharedBuildError, OSError, ValueError) as exc:
        print(f"ipq-shared-build: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
