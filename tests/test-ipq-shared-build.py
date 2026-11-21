#!/usr/bin/env python3
import json
import importlib.util
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sh"))
_spec = importlib.util.spec_from_file_location("ipq_shared_build", ROOT / "sh" / "ipq-shared-build.py")
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


def write_metadata(root: Path, package_names, kconfig_symbols=()):
    package_names = sorted(set(package_names) | {"base-files"})
    tmp = root / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in package_names:
        lines.append(f"Package: {p}")
        lines.append("Version: 1-r0")
        lines.append("Depends: +libc")
        lines.append("Title: fixture")
        lines.append("@@")
        lines.append("")
    for sym in kconfig_symbols:
        lines.append("Config:")
        lines.append(f"config PACKAGE_{sym}")
        lines.append('\tbool "fixture suboption"')
        lines.append("")
    (tmp / ".packageinfo").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config(root: Path, name: str, lines: str) -> None:
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    p = cfg_dir / name
    if p.exists():
        p.unlink()
    p.write_text(lines)


class SharedConfigTests(unittest.TestCase):
    def test_explicit_feature_enable_disable_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, [], ["luci-app-common_INCLUDE_OPTION"])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_luci-app-common_INCLUDE_OPTION=y\n")
            write_config(root, "jdcax6600.config", "# CONFIG_PACKAGE_luci-app-common_INCLUDE_OPTION is not set\n")
            with self.assertRaisesRegex(h.SharedBuildError, "scalar conflicts"):
                h.generate_shared_config(root, list(h.DEVICE_SPECS), source_root=root)

    def test_missing_metadata_cannot_fall_back_to_source_names(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package").mkdir()
            (root / "package/Makefile").write_text("PKG_NAME:=not-a-binary\n")
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_not-a-binary=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_not-a-binary=y\n")
            with self.assertRaisesRegex(h.SharedBuildError, "package metadata"):
                h.generate_shared_config(root, list(h.DEVICE_SPECS), source_root=root)

    def _pkg_line_tokens(self, text: str, profile: str):
        prefix = f"CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_{profile}="
        line = next(l for l in text.splitlines() if l.startswith(prefix))
        value = line.split("=", 1)[1].strip().strip('"')
        return value.split()

    def _write_docker(self, root: Path) -> None:
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "config" / "docker-ipq.config").write_text(
            "CONFIG_PACKAGE_docker=m\n"
            "CONFIG_PACKAGE_dockerd=m\n"
            "CONFIG_PACKAGE_luci-app-dockerman=y\n"
        )

    def test_scalar_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["docker"], [])
            write_config(root, "axt1800.config", "CONFIG_COREMARK_NUMBER_OF_THREADS=4\n")
            write_config(root, "jdcax6600.config", "CONFIG_COREMARK_NUMBER_OF_THREADS=8\n")
            with self.assertRaises(h.SharedBuildError) as ctx:
                h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root)
            self.assertIn("CONFIG_COREMARK_NUMBER_OF_THREADS", str(ctx.exception))

    def test_numeric_scalar_kept(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, [], [])
            write_config(root, "axt1800.config", "CONFIG_COREMARK_NUMBER_OF_THREADS=4\n")
            write_config(root, "jdcax6600.config", "CONFIG_COREMARK_NUMBER_OF_THREADS=4\n")
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            self.assertIn("CONFIG_COREMARK_NUMBER_OF_THREADS=4", Path(res["config"]).read_text())

    def test_multi_profile_selectors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, [], [])
            cfg_a = "CONFIG_TARGET_qualcommax=y\nCONFIG_TARGET_qualcommax_ipq60xx=y\nCONFIG_TARGET_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800=y\n"
            cfg_b = "CONFIG_TARGET_qualcommax=y\nCONFIG_TARGET_qualcommax_ipq60xx=y\nCONFIG_TARGET_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02=y\n"
            write_config(root, "axt1800.config", cfg_a)
            write_config(root, "jdcax6600.config", cfg_b)
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            lines = Path(res["config"]).read_text().splitlines()
            self.assertIn("CONFIG_TARGET_MULTI_PROFILE=y", lines)
            self.assertIn("CONFIG_TARGET_PER_DEVICE_ROOTFS=y", lines)
            self.assertIn("CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800=y", lines)
            self.assertIn("CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02=y", lines)
            self.assertFalse(any("CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800=y" == l for l in lines))

    def test_common_y_stays_global_y(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["luci-app-passwall2"], [])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_luci-app-passwall2=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_luci-app-passwall2=y\n")
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            self.assertIn("CONFIG_PACKAGE_luci-app-passwall2=y", text)
            self.assertIn("luci-app-passwall2", self._pkg_line_tokens(text, "glinet_gl-axt1800"))
            self.assertIn("luci-app-passwall2", self._pkg_line_tokens(text, "jdcloud_re-cs-02"))

    def test_exclusive_y_demoted_to_m_and_not_leaked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["luci-app-only-a", "luci-app-common"], [])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-only-a=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_luci-app-common=y\n")
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            self.assertIn("CONFIG_PACKAGE_luci-app-only-a=m", text)
            axt = set(self._pkg_line_tokens(text, "glinet_gl-axt1800"))
            jdc = set(self._pkg_line_tokens(text, "jdcloud_re-cs-02"))
            self.assertIn("luci-app-only-a", axt)
            self.assertNotIn("luci-app-only-a", jdc)
            self.assertIn("luci-app-common", axt)
            self.assertIn("luci-app-common", jdc)

    def test_explicit_m_not_added_as_install_positive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["docker", "luci-app-dockerman"], [])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_docker=m\nCONFIG_PACKAGE_luci-app-dockerman=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_docker=m\nCONFIG_PACKAGE_luci-app-dockerman=y\n")
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            tokens = self._pkg_line_tokens(text, "glinet_gl-axt1800")
            self.assertIn("luci-app-dockerman", tokens)
            self.assertNotIn("docker", tokens)
            self.assertIn("CONFIG_PACKAGE_docker=m", text)

    def test_explicit_disabled_package_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["shadowsocks-libev-ss-local", "shadowsocks-rust-sslocal"], [])
            cfg = "CONFIG_PACKAGE_shadowsocks-libev-ss-local=y\n# CONFIG_PACKAGE_shadowsocks-rust-sslocal is not set\n"
            write_config(root, "axt1800.config", cfg)
            write_config(root, "jdcax6600.config", cfg)
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            for profile in ("glinet_gl-axt1800", "jdcloud_re-cs-02"):
                tokens = self._pkg_line_tokens(text, profile)
                self.assertIn("-shadowsocks-rust-sslocal", tokens)
                self.assertIn("shadowsocks-libev-ss-local", tokens)

    def test_package_suboption_not_written_as_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["luci-app-passwall2"], ["luci-app-passwall2_INCLUDE_Haproxy", "luci-app-passwall2_Nftables_Transparent_Proxy"])
            cfg = (
                "CONFIG_PACKAGE_luci-app-passwall2=y\n"
                "CONFIG_PACKAGE_luci-app-passwall2_INCLUDE_Haproxy=y\n"
                "CONFIG_PACKAGE_luci-app-passwall2_Nftables_Transparent_Proxy=y\n"
            )
            write_config(root, "axt1800.config", cfg)
            write_config(root, "jdcax6600.config", cfg)
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            self.assertIn("CONFIG_PACKAGE_luci-app-passwall2_INCLUDE_Haproxy=y", text)
            for profile in ("glinet_gl-axt1800", "jdcloud_re-cs-02"):
                self.assertNotIn("luci-app-passwall2_INCLUDE_Haproxy", self._pkg_line_tokens(text, profile))
                self.assertIn("luci-app-passwall2", self._pkg_line_tokens(text, profile))

    def test_docker_override_and_install_intent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, ["docker", "dockerd", "luci-app-dockerman"], [])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_docker=y\nCONFIG_PACKAGE_dockerd=y\nCONFIG_PACKAGE_luci-app-dockerman=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_docker=y\nCONFIG_PACKAGE_dockerd=y\nCONFIG_PACKAGE_luci-app-dockerman=y\n")
            self._write_docker(root)
            res = h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], docker=True, source_root=root, out=root / "c")
            text = Path(res["config"]).read_text()
            self.assertIn("CONFIG_PACKAGE_docker=m", text)
            self.assertIn("CONFIG_PACKAGE_dockerd=m", text)
            self.assertIn("CONFIG_PACKAGE_luci-app-dockerman=y", text)
            for profile in ("glinet_gl-axt1800", "jdcloud_re-cs-02"):
                tokens = self._pkg_line_tokens(text, profile)
                self.assertIn("luci-app-dockerman", tokens)
                self.assertNotIn("docker", tokens)
                self.assertNotIn("dockerd", tokens)

    def test_unknown_package_like_symbol_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_metadata(root, [], [])
            write_config(root, "axt1800.config", "CONFIG_PACKAGE_missing-package=y\n")
            write_config(root, "jdcax6600.config", "CONFIG_PACKAGE_missing-package=y\n")
            with self.assertRaises(h.SharedBuildError) as ctx:
                h.generate_shared_config(root, ["AXT-1800", "JDC-AX6600"], source_root=root)
            self.assertIn("missing-package", str(ctx.exception))


class SplitOutputsTests(unittest.TestCase):
    def _make_source(self, dst: Path):
        (dst).mkdir(parents=True)
        img_sha = [hashlib.sha256(b"x" * 16).hexdigest(), hashlib.sha256(b"x" * 16).hexdigest()]
        images = ["openwrt-ipq60xx-glinet_gl-axt1800-sysupgrade.bin", "openwrt-ipq60xx-jdcloud_re-cs-02-factory.bin"]
        for img in images:
            (dst / img).write_bytes(b"x" * 16)
        (dst / (images[0] + ".sha256sum")).write_text(img_sha[0] + "\n")
        (dst / (images[1] + ".sha256sum")).write_text(img_sha[1] + "\n")
        (dst / "config.buildinfo").write_text("CONFIG_PACKAGE_fixture=y\n")
        (dst / "feeds.buildinfo").write_text("src-git fixture https://example.invalid/fixture.git\n")
        (dst / "version.buildinfo").write_text("fixture-1\n")
        (dst / "profiles.json").write_text(json.dumps({
            "metadata_version": "1",
            "profiles": {
                "glinet_gl-axt1800": {
                    "image_prefix": "openwrt-ipq60xx-glinet_gl-axt1800",
                    "images": [{"name": images[0], "sha256": img_sha[0]}],
                    "device_packages": ["bash"],
                    "titles": [{"title": "AXT"}],
                },
                "jdcloud_re-cs-02": {
                    "image_prefix": "openwrt-ipq60xx-jdcloud_re-cs-02",
                    "images": [{"name": images[1], "sha256": img_sha[1]}],
                    "device_packages": ["aria2"],
                    "titles": [{"title": "JDC"}],
                },
            },
        }))
        (dst / "openwrt-ipq60xx-glinet_gl-axt1800.manifest").write_text("bash - 1.2.3\n")
        (dst / "openwrt-ipq60xx-jdcloud_re-cs-02.manifest").write_text("aria2 - 1.2.3\n")

    def test_split_realistic_cross_device_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            res = h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])
            self.assertIn("AXT-1800", res)
            self.assertIn("JDC-AX6600", res)
            axt = dst / "firmware-AXT-1800"
            jdc = dst / "firmware-JDC-AX6600"
            self.assertTrue((axt / "openwrt-ipq60xx-glinet_gl-axt1800-sysupgrade.bin").exists())
            self.assertTrue((jdc / "openwrt-ipq60xx-jdcloud_re-cs-02-factory.bin").exists())
            self.assertFalse((axt / "openwrt-ipq60xx-jdcloud_re-cs-02-factory.bin").exists())
            self.assertFalse((jdc / "openwrt-ipq60xx-glinet_gl-axt1800-sysupgrade.bin").exists())
            self.assertTrue((axt / "openwrt-ipq60xx-glinet_gl-axt1800.manifest").exists())
            self.assertTrue((jdc / "openwrt-ipq60xx-jdcloud_re-cs-02.manifest").exists())
            self.assertFalse((axt / "openwrt-ipq60xx-jdcloud_re-cs-02.manifest").exists())
            self.assertFalse((jdc / "openwrt-ipq60xx-glinet_gl-axt1800.manifest").exists())
            self.assertTrue((axt / "config.buildinfo").exists())
            self.assertTrue((jdc / "config.buildinfo").exists())
            for directory, profile in ((axt, "glinet_gl-axt1800"), (jdc, "jdcloud_re-cs-02")):
                self.assertEqual(set(json.loads((directory / "profiles.json").read_text())["profiles"]), {profile})
                sums = {}
                for line in (directory / "sha256sums").read_text().splitlines():
                    digest, name = line.split(" *", 1)
                    sums[name] = digest
                    self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(set(sums), {p.name for p in directory.iterdir()} - {"sha256sums"})

    def test_release_metadata_renaming_keeps_checksums_valid(self):
        if yaml is None:
            self.skipTest("pyyaml not available")
        action = yaml.safe_load(
            (ROOT / ".github/actions/openwrt-publish-release/action.yml").read_text())
        script = next(step["run"] for step in action["runs"]["steps"]
                      if step.get("name") == "Prefix generic firmware metadata files")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            self._make_source(src)
            out = root / "all-artifacts"
            h.split_outputs(src, out, list(h.DEVICE_SPECS))
            # Native checksums may use text mode, while shared outputs use binary mode.
            jdc_sums = out / "firmware-JDC-AX6600/sha256sums"
            jdc_sums.write_text(jdc_sums.read_text().replace(" *", "  "))
            result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for device in h.DEVICE_SPECS:
                directory = out / ("firmware-" + device)
                sums = directory / (device + "-sha256sums")
                check = subprocess.run(["sha256sum", "--check", sums.name],
                                       cwd=directory, capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
                for name in ("version.buildinfo", "profiles.json", "config.buildinfo", "feeds.buildinfo"):
                    self.assertTrue((directory / (device + "-" + name)).is_file())
                self.assertTrue(list(directory.glob("openwrt-*.manifest")))
                self.assertTrue(list(directory.glob("openwrt-*.bin")))

    def test_split_missing_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            (src / "profiles.json").write_text(json.dumps({"profiles": {}}))
            with self.assertRaises(h.SharedBuildError):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_split_missing_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            (src / "openwrt-ipq60xx-glinet_gl-axt1800.manifest").unlink()
            with self.assertRaises(h.SharedBuildError):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_split_missing_image_prefix_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            data = json.loads((src / "profiles.json").read_text())
            del data["profiles"]["glinet_gl-axt1800"]["image_prefix"]
            (src / "profiles.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(h.SharedBuildError, "image_prefix"):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_split_unsafe_filename(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            data = json.loads((src / "profiles.json").read_text())
            data["profiles"]["glinet_gl-axt1800"]["images"][0]["name"] = "../../etc/passwd"
            (src / "profiles.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(h.SharedBuildError, "unsafe filename"):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_split_manifest_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            (src / ".." / "outside.manifest").write_text("outside\n")
            data = json.loads((src / "profiles.json").read_text())
            data["profiles"]["glinet_gl-axt1800"]["image_prefix"] = "../outside"
            (src / "profiles.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(h.SharedBuildError, "unsafe image_prefix"):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_cross_device_image_reference_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            self._make_source(src)
            data = json.loads((src / "profiles.json").read_text())
            data["profiles"]["glinet_gl-axt1800"]["images"] = data["profiles"]["jdcloud_re-cs-02"]["images"]
            (src / "profiles.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(h.SharedBuildError, "does not belong"):
                h.split_outputs(src, root / "dst", list(h.DEVICE_SPECS))

    def test_split_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            outside = root / "outside.bin"
            outside.write_bytes(b"evil" * 32)
            os_symlink = getattr(os, "symlink", None)
            if os_symlink is None:
                self.skipTest("no symlink support")
            os_symlink(str(outside), str(src / "evil.bin"))
            (src / "profiles.json").write_text(json.dumps({
                "profiles": {
                    "glinet_gl-axt1800": {
                        "image_prefix": "openwrt-ipq60xx-glinet_gl-axt1800",
                        "images": [{"name": "evil.bin", "sha256": hashlib.sha256(b"evil" * 32).hexdigest()}],
                        "titles": [],
                    },
                },
            }))
            with self.assertRaises(h.SharedBuildError):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])

    def test_split_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src"
            dst = root / "dst"
            self._make_source(src)
            (src / "openwrt-ipq60xx-glinet_gl-axt1800-sysupgrade.bin").write_bytes(b"y" * 32)
            with self.assertRaises(h.SharedBuildError):
                h.split_outputs(src, dst, ["AXT-1800", "JDC-AX6600"])


class PackageListTests(unittest.TestCase):
    def test_distinct_package_lists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a.manifest"
            b = root / "b.manifest"
            a.write_text("luci-app-passwall2 - 1\nluci-app-mosdns - 2\n")
            b.write_text("luci-app-aria2 - 3\nluci-app-mosdns - 2\n")
            pa = h.extract_package_list(a, root / "a.txt")
            pb = h.extract_package_list(b, root / "b.txt")
            self.assertEqual(pa.read_text().splitlines(), ["luci-app-mosdns", "luci-app-passwall2"])
            self.assertEqual(pb.read_text().splitlines(), ["luci-app-aria2", "luci-app-mosdns"])

    def test_empty_flavor_includes_all_manifest_packages_and_default_stays_luci_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "device.manifest"
            manifest.write_text(
                "base-files - 1\n"
                "kernel - 2\n"
                "luci-app-firewall - 3\n"
                "kmod-ath11k - 4\n"
            )

            luci = h.extract_package_list(manifest, root / "packages.txt")
            full = h.extract_package_list(
                manifest, root / "packages-full.txt", flavor=""
            )

            self.assertEqual(luci.read_text().splitlines(), ["luci-app-firewall"])
            self.assertEqual(
                full.read_text().splitlines(),
                ["base-files", "kernel", "kmod-ath11k", "luci-app-firewall"],
            )


class ManifestRuleTests(unittest.TestCase):
    def test_make_reads_each_device_rootfs_and_propagates_apk_errors(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "include").mkdir()
            (root / "include/image.mk").write_text("define Device/Build\nendef\n")
            (root / ".config").write_text(
                "CONFIG_USE_APK=y\nCONFIG_TARGET_MULTI_PROFILE=y\nCONFIG_TARGET_PER_DEVICE_ROOTFS=y\n")
            h.patch_manifest_rules(root)
            first = (root / "include/image.mk").read_bytes()
            h.patch_manifest_rules(root)
            self.assertEqual(first, (root / "include/image.mk").read_bytes())
            (root / "bin").mkdir()
            for label in ("a", "b"):
                directory = root / ("roots/target-dir-" + label)
                directory.mkdir(parents=True)
                (directory / "fixture.packages").write_text("base-files 1\nluci-app-only-" + label + " 2\n")
            apk = root / "mock-apk"
            apk.write_text('#!/bin/sh\ncat "$1/fixture.packages"\n')
            apk.chmod(0o755)
            (root / "Makefile").write_text(
                f"BIN_DIR := {root}/bin\nKDIR := {root}/roots\n"
                f"apk = {apk} $(1)\n"
                "TARGET_PER_DEVICE_ROOTFS := 1\n_PROFILE_SET := y\n_TARGET := all\n"
                "include include/image.mk\n"
                "ROOTFS_ID/glinet_gl-axt1800 := a\nROOTFS_ID/jdcloud_re-cs-02 := b\n"
                "DEVICE_IMG_PREFIX := openwrt-glinet_gl-axt1800\n"
                "$(eval $(call Device/Build,glinet_gl-axt1800))\n"
                "DEVICE_IMG_PREFIX := openwrt-jdcloud_re-cs-02\n"
                "$(eval $(call Device/Build,jdcloud_re-cs-02))\n"
                "target-dir-a target-dir-b image_prepare:\n\t@true\n")
            run = subprocess.run(["make", "-j2", "all"], cwd=root, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            a = root / "bin/openwrt-glinet_gl-axt1800.manifest"
            b = root / "bin/openwrt-jdcloud_re-cs-02.manifest"
            self.assertEqual(a.read_text(), "base-files - 1\nluci-app-only-a - 2\n")
            self.assertEqual(b.read_text(), "base-files - 1\nluci-app-only-b - 2\n")
            a.unlink()
            apk.write_text("#!/bin/sh\nexit 7\n")
            failed = subprocess.run(["make", "all"], cwd=root, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(a.exists())


class WorkflowStructureTests(unittest.TestCase):
    def test_prepare_step_executes_in_both_modes(self):
        if yaml is None:
            self.skipTest("pyyaml not available")
        workflow = yaml.safe_load((ROOT / ".github/workflows/_openwrt-build-device.yml").read_text())
        steps = workflow["jobs"]["build"]["steps"]
        prepare = next(s["run"] for s in steps if s.get("name") == "Apply custom config and run custom script part 2")
        audit = next(s["run"] for s in steps if s.get("name") == "Audit shared normalized package intent")
        for shared in (False, True):
            with self.subTest(shared=shared), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = root / "openwrt"
                (source / "scripts").mkdir(parents=True)
                (source / "include").mkdir()
                (source / "include/image.mk").write_text("define Device/Build\nendef\n")
                (source / "scripts/diffconfig.sh").write_text("#!/bin/sh\nexit 0\n")
                (source / "scripts/diffconfig.sh").chmod(0o755)
                (root / "sh").mkdir()
                shutil.copy2(ROOT / "sh/ipq-shared-build.py", root / "sh/ipq-shared-build.py")
                part2 = root / "sh/part2.sh"
                part2.write_text(
                    "#!/bin/bash\nset -e\n"
                    'if [ "$EXPECT_SINGLE" = true ]; then grep -q CONFIG_PACKAGE_luci-app-extra=y .config; fi\n'
                    'touch "$PWD/part2-ran"\n'
                )
                for device, spec in h.DEVICE_SPECS.items():
                    write_config(root, Path(spec["config"]).name,
                        "CONFIG_TARGET_qualcommax=y\nCONFIG_TARGET_qualcommax_ipq60xx=y\n"
                        "CONFIG_USE_APK=y\n"
                        f"CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_{spec['profile']}=y\n"
                        "CONFIG_PACKAGE_luci-app-common=y\n")
                write_config(root, "extra.config", "CONFIG_PACKAGE_luci-app-extra=y\n")
                write_config(root, "docker-ipq.config", "CONFIG_PACKAGE_luci-app-docker=y\n")
                write_metadata(source, ["luci-app-common", "luci-app-extra", "luci-app-docker"])
                mockbin = root / "mockbin"
                mockbin.mkdir()
                make = mockbin / "make"
                make.write_text("#!/bin/sh\ntest -f part2-ran || exit 8\n")
                make.chmod(0o755)
                inputs = {
                    "default_setting": "missing-default",
                    "diy_p2_sh": "sh/part2.sh",
                    "config_file": "config/axt1800.config",
                    "extra_config_file": "config/extra.config",
                    "shared_build": str(shared).lower(),
                    "shared_docker": str(shared).lower(),
                    "producer_validation": "false",
                }
                def render(script):
                    for key, value in inputs.items():
                        script = script.replace("${{ inputs." + key + " }}", value)
                    self.assertNotIn("${{", script)
                    return script
                env = {**os.environ, "GITHUB_WORKSPACE": str(root),
                       "EXPECT_SINGLE": str(not shared).lower(),
                       "PYTHONDONTWRITEBYTECODE": "1",
                       "PATH": str(mockbin) + os.pathsep + os.environ["PATH"]}
                run = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", render(prepare)],
                                     cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                result = (source / ".config").read_text()
                self.assertIn("CONFIG_PACKAGE_luci-app-common=y", result)
                if shared:
                    self.assertIn("CONFIG_TARGET_MULTI_PROFILE=y", result)
                    self.assertIn("CONFIG_PACKAGE_luci-app-docker=y", result)
                    audited = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", render(audit)],
                                             cwd=root, env=env, capture_output=True, text=True)
                    self.assertEqual(audited.returncode, 0, audited.stdout + audited.stderr)
                else:
                    self.assertIn("CONFIG_PACKAGE_luci-app-extra=y", result)

    def test_dispatch_to_workflow_call_boolean_flow(self):
        root = ROOT / ".github" / "workflows"
        shared = root / "Build IPQ-60xx.yml"
        reusable = root / "_openwrt-build-device.yml"
        self.assertTrue(shared.is_file())
        self.assertTrue(reusable.is_file())
        self.assertFalse((root / "Build IPQ-60xx Shared.yml").exists())
        if yaml is None:
            self.skipTest("pyyaml not available")
        d = yaml.safe_load(shared.read_text())
        events = d.get("on", d.get(True, {}))
        self.assertTrue({"workflow_dispatch", "repository_dispatch", "schedule"} <= set(events))
        jobs = d.get("jobs", {})
        self.assertEqual(set(jobs), {"producer", "image", "publish_release"})
        self.assertNotIn("strategy", jobs["producer"])
        self.assertEqual(jobs["producer"]["uses"], "./.github/workflows/_openwrt-build-device.yml")
        with_inputs = jobs["producer"].get("with", {})
        self.assertEqual(with_inputs["workflow_name"], "IPQ60xx-Shared")
        self.assertEqual(with_inputs.get("shared_build"), True)
        self.assertEqual(with_inputs.get("shared_docker"), "${{ github.event.inputs.docker == 'true' }}")
        self.assertEqual(with_inputs.get("producer_validation"), True)
        self.assertNotIn("${{ env.", with_inputs.get("repo_url", ""))
        self.assertEqual(jobs["image"]["needs"], "producer")
        self.assertEqual(
            jobs["image"]["strategy"]["matrix"]["include"],
            [
                {"profile": "glinet_gl-axt1800", "device": "AXT-1800"},
                {"profile": "jdcloud_re-cs-02", "device": "JDC-AX6600"},
            ],
        )
        image_steps = jobs["image"]["steps"]
        download = next(
            step for step in image_steps
            if step.get("name") == "Download producer ImageBuilder artifact"
        )
        self.assertEqual(
            download["with"]["name"],
            "ipq-imagebuilder-producer-${{ github.run_id }}",
        )
        build_image = next(
            step for step in image_steps
            if step.get("name") == "Build and verify device image"
        )
        self.assertIn('make manifest "PROFILE=$PROFILE" "PACKAGES=$PACKAGE_ARGS"', build_image["run"])
        self.assertIn('make image "PROFILE=$PROFILE" "PACKAGES=$PACKAGE_ARGS"', build_image["run"])
        self.assertIn("ipq-imagebuilder-consumer.py", build_image["run"])
        upload_names = {
            step["with"]["name"]
            for step in image_steps
            if step.get("uses") == "actions/upload-artifact@main"
        }
        self.assertEqual(
            upload_names,
            {"firmware-${{ matrix.device }}", "package-list-${{ matrix.device }}"},
        )
        for upload in image_steps:
            if upload.get("uses") == "actions/upload-artifact@main":
                self.assertTrue(upload["with"]["overwrite"])
        package_step = next(
            step for step in image_steps
            if step.get("name") == "Build and verify device image"
        )
        self.assertIn('--out "$PACKAGE_LIST_DIR/packages.txt"', package_step["run"])
        self.assertIn('--out "$PACKAGE_LIST_DIR/packages-full.txt"', package_step["run"])
        self.assertIn('--flavor ""', package_step["run"])
        package_upload = next(
            step for step in image_steps
            if step.get("name") == "Upload device package list artifact"
        )
        self.assertIn("/package-list-${{ matrix.device }}/*", package_upload["with"]["path"])
        self.assertEqual(jobs["publish_release"]["needs"], "image")
        self.assertEqual(
            jobs["publish_release"]["steps"][-1]["uses"],
            "./.github/actions/openwrt-publish-release",
        )
        publish_action = yaml.safe_load(
            (ROOT / ".github/actions/openwrt-publish-release/action.yml").read_text()
        )
        release_body_script = next(
            step["run"] for step in publish_action["runs"]["steps"]
            if step.get("name") == "Generate release tag and body"
        )
        self.assertIn("### LuCI package list", release_body_script)
        self.assertIn('"$dir/packages.txt"', release_body_script)
        self.assertIn('"$dir/packages-full.txt"', release_body_script)
        self.assertRegex(
            release_body_script,
            r'(?s)full_package_heading_written=false.*?'
            r'\[ -f "\$dir/packages-full\.txt" \] \|\| continue.*?'
            r'if \[ "\$full_package_heading_written" = false \]; then\s+'
            r'echo "" >> release-body\.md\s+'
            r'echo "### Full package list \(from image manifest\)" >> release-body\.md\s+'
            r'full_package_heading_written=true\s+fi',
        )

        r = yaml.safe_load(reusable.read_text())
        steps = r["jobs"]["build"]["steps"]
        text = str(steps)
        self.assertNotIn("inputs.shared_build == 'true'", text)
        self.assertNotIn("inputs.shared_docker == 'true'", text)
        self.assertIn("make prepare-tmpinfo", text)
        audit_steps = [s for s in steps if "audit" in s.get("name", "").lower()]
        self.assertTrue(audit_steps, "audit step should be present")
        self.assertEqual(audit_steps[0]["if"], "${{ inputs.shared_build }}")

    def test_manual_producer_validation_workflow_is_isolated(self):
        if yaml is None:
            self.skipTest("pyyaml not available")
        workflows = ROOT / ".github/workflows"
        path = workflows / "Validate IPQ ImageBuilder Producer.yml"
        self.assertTrue(path.is_file(), "manual producer validation workflow is required")
        workflow = yaml.safe_load(path.read_text())
        events = workflow.get("on", workflow.get(True, {}))
        self.assertEqual(set(events), {"push", "workflow_dispatch"})
        self.assertEqual(events["push"]["branches"], ["feat/ipq-shared-build"])
        jobs = workflow.get("jobs", {})
        self.assertEqual(set(jobs), {"producer"})
        producer_job = jobs["producer"]
        self.assertEqual(
            producer_job["uses"], "./.github/workflows/_openwrt-build-device.yml"
        )
        inputs = producer_job["with"]
        self.assertEqual(inputs["workflow_name"], "IPQ60xx-Shared")
        self.assertEqual(inputs["shared_build"], True)
        self.assertEqual(inputs["producer_validation"], True)
        self.assertNotIn("publish", str(jobs).lower())

        reusable = yaml.safe_load(
            (workflows / "_openwrt-build-device.yml").read_text()
        )
        reusable_events = reusable.get("on", reusable.get(True, {}))
        reusable_inputs = reusable_events["workflow_call"]["inputs"]
        self.assertEqual(reusable_inputs["producer_validation"]["default"], False)
        steps = reusable["jobs"]["build"]["steps"]
        names = [step.get("name", "") for step in steps]
        compile_index = names.index("Compile firmware")
        produce_index = names.index("Stage and validate IPQ ImageBuilder producer")
        upload_index = names.index("Upload IPQ ImageBuilder producer artifact")
        cleanup_index = names.index("Remove temporary build files")
        self.assertLess(compile_index, produce_index)
        self.assertLess(produce_index, upload_index)
        self.assertLess(upload_index, cleanup_index)
        stage = steps[produce_index]
        self.assertEqual(stage["if"], "${{ inputs.producer_validation }}")
        for symbol in ("CONFIG_IB", "CONFIG_IB_STANDALONE", "CONFIG_USE_APK"):
            self.assertIn(symbol, stage["run"])
        prepare = next(
            step["run"]
            for step in steps
            if step.get("name") == "Apply custom config and run custom script part 2"
        )
        self.assertIn("Producer validation requires shared_build=true", prepare)
        self.assertIn("'CONFIG_IB=y'", prepare)
        self.assertIn("'CONFIG_IB_STANDALONE=y'", prepare)
        self.assertIn("'CONFIG_USE_APK=y'", prepare)
        self.assertIn("ipq-imagebuilder-producer.py", stage["run"])
        self.assertIn('PRIVATE_KEY="$PWD/private-key.pem"', stage["run"])
        stage_run = stage["run"]
        reset_index = stage_run.index('rm -f "$BUNDLE/imagebuilder/packages/packages.adb"')
        rebuild_index = stage_run.index('make -C "$BUNDLE/imagebuilder" package_index V=s')
        clear_key_trap = stage_run.index("trap - EXIT")
        package_intent = stage_run.index('ipq-imagebuilder-producer.py" package-intent')
        repack = stage_run.index(' -cf "$BUNDLE/imagebuilder.repacked.tar.zst"')
        self.assertLess(reset_index, rebuild_index)
        self.assertLess(rebuild_index, clear_key_trap)
        self.assertLess(clear_key_trap, package_intent)
        self.assertLess(package_intent, repack)
        self.assertIn("Producer validation requires shared_build=true", prepare)
        self.assertIn("ARCHIVE_LIST=\"$(mktemp", stage["run"])
        self.assertIn(" -tf \"$BUNDLE/imagebuilder.tar.zst\" > \"$ARCHIVE_LIST\"", stage["run"])
        self.assertNotIn(
            'tar -I "$ZSTD -d" -tf "$BUNDLE/imagebuilder.tar.zst" \\\n'
            '              | grep -Fxq',
            stage["run"],
        )
        upload = steps[upload_index]
        self.assertEqual(upload["if"], "${{ inputs.producer_validation }}")
        self.assertEqual(upload["uses"], "actions/upload-artifact@main")
        for step in steps:
            if step.get("name", "").startswith("Upload ") and step is not upload:
                self.assertIn("!inputs.producer_validation", step.get("if", ""))


class NormalizedAuditTests(unittest.TestCase):
    def _write_source(self, root: Path, axt: str, jdc: str, packages, subopts=()):
        write_metadata(root, packages, subopts)
        write_config(root, "axt1800.config", axt)
        write_config(root, "jdcax6600.config", jdc)

    def _normalized(self, root: Path, package_flags: str, axt_tokens: str, jdc_tokens: str) -> Path:
        norm = root / "normalized.config"
        norm.write_text(
            "CONFIG_TARGET_qualcommax_ipq60xx=y\n"
            "CONFIG_TARGET_MULTI_PROFILE=y\n"
            "CONFIG_TARGET_PER_DEVICE_ROOTFS=y\n"
            "CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800=y\n"
            "CONFIG_TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02=y\n"
            + package_flags
            + f'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800="{axt_tokens}"\n'
            + f'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02="{jdc_tokens}"\n'
        )
        return norm

    def test_audit_accepts_real_normalized_intent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_source(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-only-a=y\n# CONFIG_PACKAGE_luci-app-neg is not set\n",
                "CONFIG_PACKAGE_luci-app-common=y\n",
                ["luci-app-common", "luci-app-only-a", "luci-app-neg"],
            )
            norm = self._normalized(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-only-a=m\nCONFIG_PACKAGE_luci-app-neg=m\n",
                "luci-app-common luci-app-only-a -luci-app-neg",
                "luci-app-common",
            )
            problems = h.audit_normalized_packages(root, norm, source_root=root)
            self.assertEqual(problems, [])

    def test_audit_rejects_exclusive_promoted_to_y(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_source(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-only-a=y\n",
                "CONFIG_PACKAGE_luci-app-common=y\n",
                ["luci-app-common", "luci-app-only-a"],
            )
            norm = self._normalized(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-only-a=y\n",
                "luci-app-common luci-app-only-a",
                "luci-app-common",
            )
            problems = h.audit_normalized_packages(root, norm, source_root=root)
            self.assertTrue(any("luci-app-only-a" in p and "leaks" in p for p in problems))

    def test_audit_rejects_missing_compiled_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_source(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\n",
                "CONFIG_PACKAGE_luci-app-common=y\n",
                ["luci-app-common"],
            )
            norm = self._normalized(root, "", "luci-app-common", "luci-app-common")
            problems = h.audit_normalized_packages(root, norm, source_root=root)
            self.assertTrue(any("compiled flag missing" in p for p in problems))

    def test_audit_rejects_missing_negative_token(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_source(
                root,
                "CONFIG_PACKAGE_luci-app-common=y\n# CONFIG_PACKAGE_luci-app-neg is not set\n",
                "CONFIG_PACKAGE_luci-app-common=y\n",
                ["luci-app-common", "luci-app-neg"],
            )
            norm = self._normalized(root, "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_luci-app-neg=m\n", "luci-app-common", "luci-app-common")
            problems = h.audit_normalized_packages(root, norm, source_root=root)
            self.assertTrue(any("negative" in p and "luci-app-neg" in p for p in problems))

    def test_audit_docker_install_not_positive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "config" / "docker-ipq.config").write_text(
                "CONFIG_PACKAGE_docker=m\nCONFIG_PACKAGE_luci-app-dockerman=y\n"
            )
            self._write_source(
                root,
                "CONFIG_PACKAGE_docker=y\nCONFIG_PACKAGE_luci-app-dockerman=y\n",
                "CONFIG_PACKAGE_docker=y\nCONFIG_PACKAGE_luci-app-dockerman=y\n",
                ["docker", "luci-app-dockerman"],
            )
            norm = self._normalized(
                root,
                "CONFIG_PACKAGE_docker=m\nCONFIG_PACKAGE_luci-app-dockerman=y\n",
                "luci-app-dockerman",
                "luci-app-dockerman",
            )
            problems = h.audit_normalized_packages(root, norm, source_root=root, docker=True)
            self.assertEqual(problems, [])

    def test_disabled_only_package_need_not_be_compiled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = "# CONFIG_PACKAGE_luci-app-disabled is not set\n"
            self._write_source(root, cfg, cfg, ["luci-app-disabled"])
            norm = self._normalized(root, cfg, "-luci-app-disabled", "-luci-app-disabled")
            self.assertEqual(h.audit_normalized_packages(root, norm, source_root=root), [])
            result = h.generate_shared_config(root, list(h.DEVICE_SPECS), source_root=root, out=root / "candidate")
            self.assertIn(cfg.strip(), Path(result["config"]).read_text())

    def test_dependency_baselines_allow_legitimate_common_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_source(root, "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_libdependency=y\n",
                               "CONFIG_PACKAGE_luci-app-common=y\n",
                               ["luci-app-common", "libdependency"])
            baseline = root / "baselines"
            baseline.mkdir()
            for device, spec in h.DEVICE_SPECS.items():
                (baseline / (device + ".config")).write_text(
                    f"CONFIG_TARGET_qualcommax_ipq60xx_DEVICE_{spec['profile']}=y\n"
                    "CONFIG_PACKAGE_luci-app-common=y\nCONFIG_PACKAGE_libdependency=y\n")
            result = h.generate_shared_config(root, list(h.DEVICE_SPECS), source_root=root,
                                             baseline_dir=baseline, out=root / "candidate")
            text = Path(result["config"]).read_text()
            self.assertIn("CONFIG_PACKAGE_libdependency=y", text)
            self.assertEqual(h.audit_normalized_packages(root, Path(result["config"]),
                             source_root=root, baseline_dir=baseline), [])
            broken = baseline / "AXT-1800.config"
            broken.write_text(broken.read_text().replace("CONFIG_PACKAGE_libdependency=y",
                                                       "# CONFIG_PACKAGE_libdependency is not set"))
            with self.assertRaisesRegex(h.SharedBuildError, "lost requested libdependency"):
                h.generate_shared_config(root, list(h.DEVICE_SPECS), source_root=root,
                                         baseline_dir=baseline, out=root / "broken")


if __name__ == "__main__":
    unittest.main()
