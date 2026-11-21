#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ipq_imagebuilder_producer", ROOT / "sh" / "ipq-imagebuilder-producer.py"
)
producer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(producer)


PROVENANCE = {
    "source_revision": "d913d0accfde29b619854c4e145e293d9264e7e8",
    "builder_revision": "b" * 40,
    "feeds": {"packages": "f" * 40},
    "custom_revisions": {"custom-example": "tree-sha256:" + "c" * 64},
    "target": "qualcommax/ipq60xx",
    "architecture": "aarch64_cortex-a53",
    "kernel_vermagic": "6.12.1-example",
    "package_manager": "apk",
    "build_flags": {
        "CONFIG_IB": "y",
        "CONFIG_IB_STANDALONE": "y",
        "CONFIG_USE_APK": "y",
    },
}


class ProducerBundleTests(unittest.TestCase):
    def test_package_name_validation_accepts_real_underscore_package(self):
        package = "ipq-wifi-glinet_gl-axt1800"
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "device.manifest"
            packageinfo = Path(td) / ".packageinfo"
            manifest.write_text(
                f"{package} - 2026.05.18~e20f4c6f-r1\n",
                encoding="utf-8",
            )
            packageinfo.write_text(f"Package: {package}\n", encoding="utf-8")

            self.assertEqual(
                producer._parse_package_manifest(manifest),
                {package: "2026.05.18~e20f4c6f-r1"},
            )
            self.assertEqual(set(producer._package_metadata(packageinfo)), {package})

    def test_package_name_validation_rejects_obviously_invalid_names(self):
        for package in ("_leading-underscore", "bad/name", "bad name"):
            with self.subTest(package=package):
                self.assertIsNone(producer.PACKAGE_NAME_RE.fullmatch(package))

    def _stage_fixture_apks(self, ib, packages):
        apk = ib / "staging_dir/host/bin/apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_text('#!/bin/sh\n[ "$1 $2" = "--allow-untrusted adbdump" ] && cat "$3"\n')
        apk.chmod(0o755)
        pool = ib / "packages"
        pool.mkdir(exist_ok=True)
        index = pool / "packages.adb"
        rows = index.read_text().split("\n", 2)[2] if index.exists() else ""
        for name, version, arch, *abi in packages:
            (pool / f"{name}-{version}.apk").write_bytes(b"apk")
            rows += (
                f"  - name: {name}\n    version: {version}\n"
                f"    arch: {arch}\n    file-size: 3\n"
            )
            if abi:
                base, suffix = abi
                rows += f"    provides: # 1 items\n      - {base}\n"
                rows += f"    tags: # 1 items\n      - openwrt:abiversion={suffix}\n"
        index.write_text(f"#%SCHEMA: 78646E69\npackages: # {rows.count('  - name: ')} items\n{rows}")

    def _make_bundle(self, root: Path):
        ib = root / "imagebuilder"
        (ib / "include").mkdir(parents=True)
        (ib / "target/linux/qualcommax/linux-6.12/arch/arm64/boot/dts").mkdir(
            parents=True
        )
        (ib / "target/linux/generic").mkdir(parents=True)
        (ib / "staging_dir/host/bin").mkdir(parents=True)
        (ib / "packages").mkdir()
        (ib / "keys").mkdir()
        (root / "repositories/targets/qualcommax/ipq60xx/packages").mkdir(
            parents=True
        )
        (root / "repositories/packages/aarch64_cortex-a53/base").mkdir(
            parents=True
        )
        (root / "metadata").mkdir()

        (root / "imagebuilder.tar.zst").write_bytes(b"fixture archive")
        (ib / "Makefile").write_text("include include/kernel.mk\n")
        (ib / ".config").write_text(
            "CONFIG_IB=y\nCONFIG_IB_STANDALONE=y\nCONFIG_USE_APK=y\n"
            "CONFIG_SIGNATURE_CHECK=y\nCONFIG_SIGNED_PACKAGES=y\n"
            'CONFIG_TARGET_BOARD="qualcommax"\n'
            'CONFIG_TARGET_SUBTARGET="ipq60xx"\n'
            'CONFIG_TARGET_ARCH_PACKAGES="aarch64_cortex-a53"\n'
        )
        (root / "metadata/.config").write_text((ib / ".config").read_text())
        (root / "metadata/source.config").write_text((ib / ".config").read_text())
        (ib / ".targetinfo").write_text("Target: qualcommax\n")
        (ib / ".packageinfo").write_text(
            "Package: base-files\nPackage: kmod-example\n"
            "Package: luci-app-a\nPackage: luci-app-b\n"
            "Package: luci-app-default\nPackage: kmod-axt\nPackage: kmod-jdc\n"
        )
        (root / "metadata/targetinfo").write_text((ib / ".targetinfo").read_text())
        (root / "metadata/packageinfo").write_text((ib / ".packageinfo").read_text())
        (ib / "include/kernel.mk").write_text(
            "LINUX_VERMAGIC:=6.12.1-example\n"
        )
        (ib / "target/linux/qualcommax/linux-6.12/.config").write_text(
            "CONFIG_ARM64=y\n"
        )
        (ib / "target/linux/qualcommax/linux-6.12/arch/arm64/boot/dts/"
            "qcom-ipq6018.dtb").write_bytes(b"fixture dts")
        (ib / "target/linux/qualcommax/target.mk").write_text("BOARD:=qualcommax\n")
        (ib / "target/linux/generic/config-6.12").write_text("CONFIG_NET=y\n")
        (ib / "staging_dir/host/bin/mkimage").write_bytes(b"fixture tool")
        self._stage_fixture_apks(
            ib, [("base-files", "1", "aarch64_cortex-a53"), ("kmod-example", "1", "aarch64_cortex-a53")]
        )
        (ib / "keys/openwrt-25.12.pem").write_text(
            "-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----\n"
        )
        profiles_doc = {
            "profiles": {
                "glinet_gl-axt1800": {
                    "images": ["axt1800-sysupgrade.bin"],
                    "device_packages": ["base-files", "kmod-example"],
                },
                "jdcloud_re-cs-02": {
                    "images": ["re-cs-02-sysupgrade.bin"],
                    "device_packages": ["base-files", "kmod-example"],
                },
            }
        }
        (ib / "profiles.json").write_text(
            json.dumps(profiles_doc)
        )
        (root / "metadata/profiles.json").write_text(
            json.dumps(
                profiles_doc
            )
        )
        (root / "repositories/targets/qualcommax/ipq60xx/packages/"
            "packages.adb").write_bytes(b"fixture target index")
        (root / "repositories/targets/qualcommax/ipq60xx/packages/"
            "kmod-example_1_aarch64_cortex-a53.apk").write_bytes(b"fixture kmod repository")
        (root / "repositories/packages/aarch64_cortex-a53/base/"
            "packages.adb").write_bytes(b"fixture feed index")
        (root / "repositories/packages/aarch64_cortex-a53/base/"
            "base-files_1_aarch64_cortex-a53.apk").write_bytes(b"fixture repository apk")
        manifest_dir = root / "producer-manifests"
        manifest_dir.mkdir()
        for profile_name in producer.REQUIRED_PROFILES:
            (manifest_dir / f"openwrt-{profile_name}.manifest").write_text(
                "base-files - 1\nkmod-example - 1\n"
            )
        recovery_source = root / "recovery-source"
        recovery_source.mkdir()
        for profile_name, contract in producer._image_contract().items():
            image = contract["producer_fallback"][0]
            contents = ("fixture recovery " + profile_name).encode()
            (recovery_source / image).write_bytes(contents)
        (recovery_source / "sha256sums").write_text(
            "".join(
                f"{producer._sha256(recovery_source / contract['producer_fallback'][0])}  "
                f"{contract['producer_fallback'][0]}\n"
                for profile_name, contract in producer._image_contract().items()
            )
        )
        producer.stage_recovery_images(recovery_source, root)
        producer.write_package_intent(root, ib / ".config", manifest_dir)
        producer.write_manifest(root, PROVENANCE)

    def test_valid_standalone_apk_bundle_has_complete_hash_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            (root / "imagebuilder/staging_dir/host/bin/apk").chmod(0o644)

            result = producer.validate_bundle(root)

            self.assertEqual(result["profiles"], ["glinet_gl-axt1800", "jdcloud_re-cs-02"])
            self.assertGreater(result["apk_count"], 0)
            self.assertGreater(result["kmod_count"], 0)
            self.assertGreater(result["index_count"], 0)
            self.assertTrue(result["signature_keys"])
            expected = {
                p.relative_to(root).as_posix()
                for p in root.rglob("*")
                if p.is_file() and p.name != "SHA256SUMS"
            }
            checksummed = {
                line.split("  ", 1)[1]
                for line in (root / "SHA256SUMS").read_text().splitlines()
            }
            self.assertEqual(checksummed, expected)

    def _add_host_tool_symlinks(self, root: Path):
        bin_dir = root / "imagebuilder/staging_dir/host/bin"
        os.symlink("/usr/bin/gcc", bin_dir / "gcc")
        os.symlink("no-such-toolchain", bin_dir / "cc1")
        (root / "imagebuilder/staging_dir/host/bin/self-contained").write_bytes(
            b"fixture tool"
        )
        os.symlink("self-contained", bin_dir / "zstd-link")
        host_root = root / "imagebuilder/staging_dir/host"
        (host_root / "lib").mkdir()
        (host_root / "lib/libfixture.so").write_bytes(b"fixture library")
        (host_root / "usr").mkdir()
        os.symlink("../lib", host_root / "usr/lib")
        external_dir = root.parent / f"external-host-tools-{root.name}"
        external_dir.mkdir()
        os.symlink(external_dir, host_root / "external-dir")

    def test_normalize_host_tools_removes_only_external_or_broken_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            if not hasattr(os, "symlink"):
                self.skipTest("no symlink support")
            root = Path(td)
            self._make_bundle(root)
            self._add_host_tool_symlinks(root)

            removed = producer.normalize_host_tools(root)

            self.assertEqual(
                set(removed),
                {"bin/gcc", "bin/cc1", "external-dir"},
            )
            bin_dir = root / "imagebuilder/staging_dir/host/bin"
            self.assertFalse((bin_dir / "gcc").exists())
            self.assertFalse((bin_dir / "cc1").exists())
            self.assertTrue((bin_dir / "mkimage").is_file())
            self.assertTrue((bin_dir / "self-contained").is_file())
            self.assertTrue((bin_dir / "zstd-link").is_symlink())
            self.assertTrue(
                (root / "imagebuilder/staging_dir/host/usr/lib").is_symlink()
            )
            self.assertFalse(
                (root / "imagebuilder/staging_dir/host/external-dir").exists()
            )

    def test_seal_validate_accepts_bundle_after_host_tools_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            if not hasattr(os, "symlink"):
                self.skipTest("no symlink support")
            root = Path(td)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "fixture@example.invalid"],
                check=True,
            )
            (source / "README").write_text("fixture source\n")
            subprocess.run(["git", "-C", str(source), "add", "README"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "fixture source"],
                check=True,
            )
            feed = source / "feeds/packages"
            feed.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(feed)], check=True)
            subprocess.run(
                ["git", "-C", str(feed), "config", "user.name", "Fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(feed), "config", "user.email", "fixture@example.invalid"],
                check=True,
            )
            (feed / "Makefile").write_text("feed fixture\n")
            subprocess.run(["git", "-C", str(feed), "add", "Makefile"], check=True)
            subprocess.run(
                ["git", "-C", str(feed), "commit", "-qm", "fixture feed"],
                check=True,
            )
            custom = source / "package/custom/custom-example"
            custom.mkdir(parents=True)
            (custom / "Makefile").write_text("custom fixture\n")
            bundle = root / "bundle"
            self._make_bundle(bundle)
            self._add_host_tool_symlinks(bundle)

            producer.normalize_host_tools(bundle)
            provenance = producer.collect_provenance(
                bundle,
                source,
                "qualcommax/ipq60xx",
                "aarch64_cortex-a53",
                "b" * 40,
            )
            producer.write_manifest(bundle, provenance)
            result = producer.validate_bundle(bundle)

            self.assertGreater(result["apk_count"], 0)
            self.assertTrue(
                (bundle / "imagebuilder/staging_dir/host/bin/mkimage").is_file()
            )
            self.assertFalse(
                (bundle / "imagebuilder/staging_dir/host/bin/gcc").exists()
            )
            self.assertTrue(
                (bundle / "imagebuilder/staging_dir/host/usr/lib").is_symlink()
            )

    def test_validate_accepts_internal_directory_symlink_without_duplicate_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            if not hasattr(os, "symlink"):
                self.skipTest("no symlink support")
            root = Path(td)
            self._make_bundle(root)
            host_root = root / "imagebuilder/staging_dir/host"
            (host_root / "lib").mkdir()
            (host_root / "lib/libfixture.so").write_bytes(b"fixture library")
            (host_root / "usr").mkdir()
            os.symlink("../lib", host_root / "usr/lib")

            producer.write_manifest(root, PROVENANCE)
            result = producer.validate_bundle(root)

            self.assertGreater(result["hashed_file_count"], 0)
            checksums = (root / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(checksums.count("staging_dir/host/lib/libfixture.so"), 1)
            self.assertNotIn("staging_dir/host/usr-lib/libfixture.so", checksums)

    def test_validate_rejects_external_directory_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            if not hasattr(os, "symlink"):
                self.skipTest("no symlink support")
            root = Path(td)
            self._make_bundle(root)
            outside = root.parent / f"outside-host-dir-{root.name}"
            outside.mkdir()
            producer.write_manifest(root, PROVENANCE)
            os.symlink(outside, root / "imagebuilder/staging_dir/host/external-dir")

            with self.assertRaisesRegex(
                producer.ProducerError, "symlink escapes bundle or is broken"
            ):
                producer.validate_bundle(root)

    def test_rejects_directory_symlink_in_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            if not hasattr(os, "symlink"):
                self.skipTest("no symlink support")
            root = Path(td)
            self._make_bundle(root)
            target = root.parent / f"outside-dir-{root.name}"
            target.mkdir()
            producer.write_manifest(root, PROVENANCE)
            os.symlink(target, root / "imagebuilder" / "linked-dir")

            with self.assertRaisesRegex(
                producer.ProducerError, "symlink escapes bundle or is broken"
            ):
                producer.validate_bundle(root)

    def test_collects_source_feed_custom_and_kernel_provenance_offline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / "bundle"
            self._make_bundle(bundle)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "fixture@example.invalid"],
                check=True,
            )
            (source / "README").write_text("fixture source\n")
            subprocess.run(["git", "-C", str(source), "add", "README"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "fixture source"],
                check=True,
            )

            feed = source / "feeds/packages"
            feed.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(feed)], check=True)
            subprocess.run(
                ["git", "-C", str(feed), "config", "user.name", "Fixture"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(feed), "config", "user.email", "fixture@example.invalid"],
                check=True,
            )
            (feed / "Makefile").write_text("feed fixture\n")
            subprocess.run(["git", "-C", str(feed), "add", "Makefile"], check=True)
            subprocess.run(
                ["git", "-C", str(feed), "commit", "-qm", "fixture feed"],
                check=True,
            )
            custom = source / "package/custom/custom-example"
            custom.mkdir(parents=True)
            (custom / "Makefile").write_text("custom fixture\n")

            provenance = producer.collect_provenance(
                bundle,
                source,
                "qualcommax/ipq60xx",
                "aarch64_cortex-a53",
                "b" * 40,
            )

            self.assertEqual(provenance["source_revision"], subprocess.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip())
            self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", provenance["feeds"]["packages"]))
            self.assertTrue(
                provenance["custom_revisions"]["custom-example"].startswith("tree-sha256:")
            )
            self.assertEqual(provenance["kernel_vermagic"], "6.12.1-example")
            self.assertEqual(provenance["build_flags"]["CONFIG_IB_STANDALONE"], "y")

    def test_rejects_missing_required_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            profiles = root / "imagebuilder/profiles.json"
            profiles.write_text(
                json.dumps({"profiles": {"glinet_gl-axt1800": {"images": ["x.bin"]}}})
            )
            (root / "metadata/profiles.json").write_text(profiles.read_text())
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "jdcloud_re-cs-02"):
                producer.validate_bundle(root)

    def test_rejects_missing_apk_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            for index in root.rglob("packages.adb"):
                index.unlink()
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "packages/packages.adb"):
                producer.validate_bundle(root)

    def test_rejects_missing_kmod_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            for package in root.rglob("kmod-*.apk"):
                package.unlink()
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "kmod"):
                producer.validate_bundle(root)

    def test_rejects_profile_package_absent_from_standalone_pool(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            intent_path = root / "metadata/package-intent.json"
            intent = json.loads(intent_path.read_text())
            intent["profiles"]["glinet_gl-axt1800"]["expected"].append(
                {"name": "kmod-axt", "version": "1"}
            )
            intent_path.write_text(json.dumps(intent))
            (root / "metadata/manifests/glinet_gl-axt1800.manifest").write_text(
                "base-files - 1\nkmod-example - 1\nkmod-axt - 1\n"
            )
            packageinfo = root / "imagebuilder/.packageinfo"
            packageinfo.write_text(packageinfo.read_text() + "Package: kmod-axt\n")
            (root / "metadata/packageinfo").write_text(packageinfo.read_text())
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "kmod-axt"):
                producer.validate_bundle(root)

    def test_package_intent_resolves_common_and_per_profile_packages_and_negatives(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ib = root / "imagebuilder"
            ib.mkdir()
            config = root / ".config"
            config.write_text(
                'CONFIG_TARGET_ARCH_PACKAGES="aarch64_cortex-a53"\n'
                "CONFIG_PACKAGE_base-files=y\n"
                "CONFIG_PACKAGE_kmod-common=y\n"
                "CONFIG_PACKAGE_base-internal=y\n"
                "CONFIG_PACKAGE_luci-app-a=m\n"
                "CONFIG_PACKAGE_luci-app-default=y\n"
                'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800="luci-app-a -luci-app-default"\n'
                'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02="luci-app-b"\n'
            )
            (ib / ".config").write_text(config.read_text())
            packageinfo = ib / ".packageinfo"
            packageinfo.write_text(
                "Package: base-files\n"
                "Package: kmod-common\n"
                "Package: luci-app-a\n"
                "Package: luci-app-b\n"
                "Package: luci-app-default\n"
                "Package: base-internal\n"
                "Package: default-internal\n"
            )
            profiles = ib / "profiles.json"
            profiles.write_text(
                json.dumps(
                    {
                        "default_packages": [
                            "nftables",
                            "base-files",
                            "default-internal",
                        ],
                        "profiles": {
                            "glinet_gl-axt1800": {
                                "device_packages": ["luci-app-default", "kmod-axt"]
                            },
                            "jdcloud_re-cs-02": {
                                "device_packages": ["luci-app-b", "kmod-jdc"]
                            },
                        }
                    }
                )
            )
            packageinfo.write_text(packageinfo.read_text() + "Package: kmod-axt\nPackage: kmod-jdc\n")
            self._stage_fixture_apks(ib, (
                ("base-files", "1", "aarch64_cortex-a53"),
                ("kmod-common", "2-r1", "aarch64_cortex-a53"),
                ("luci-app-a", "3", "all"),
                ("luci-app-b", "4", "noarch"),
                ("luci-app-default", "3", "all"),
                ("kmod-axt", "5", "aarch64_cortex-a53"),
                ("kmod-jdc", "6", "aarch64_cortex-a53"),
            ))
            output = root / "metadata/package-intent.json"

            manifest_dir = root / "manifests"
            manifest_dir.mkdir()
            (manifest_dir / "one-glinet_gl-axt1800.manifest").write_text(
                "base-files - 1\nkmod-common - 2-r1\nluci-app-a - 3\nkmod-axt - 5\n"
            )
            (manifest_dir / "two-jdcloud_re-cs-02.manifest").write_text(
                "base-files - 1\nkmod-common - 2-r1\nluci-app-b - 4\nluci-app-default - 3\nkmod-jdc - 6\n"
            )
            producer.write_package_intent(root, config, manifest_dir)

            intent = json.loads(output.read_text())
            self.assertEqual(
                intent["common"],
                [
                    {"name": "base-files", "version": "1"},
                    {"name": "kmod-common", "version": "2-r1"},
                    {"name": "luci-app-default", "version": "3"},
                ],
            )
            self.assertEqual(
                [item["name"] for item in intent["profiles"]["glinet_gl-axt1800"]["expected"]],
                ["base-files", "kmod-axt", "kmod-common", "luci-app-a"],
            )
            self.assertEqual(
                intent["profiles"]["glinet_gl-axt1800"]["excluded"],
                ["luci-app-default"],
            )
            self.assertEqual(
                [item["name"] for item in intent["profiles"]["jdcloud_re-cs-02"]["expected"]],
                ["base-files", "kmod-common", "kmod-jdc", "luci-app-b", "luci-app-default"],
            )
            self.assertNotIn(
                "nftables",
                [
                    item["name"]
                    for profile in intent["profiles"].values()
                    for item in profile["expected"]
                ],
            )
            self.assertNotIn(
                "base-internal",
                [item["name"] for item in intent["common"]],
            )
            self.assertNotIn(
                "default-internal",
                [
                    item["name"]
                    for profile in intent["profiles"].values()
                    for item in profile["expected"]
                ],
            )

            profiles_doc = json.loads(profiles.read_text())
            profiles_doc["profiles"]["glinet_gl-axt1800"]["device_packages"].append(
                "missing-explicit-device-package"
            )
            profiles.write_text(json.dumps(profiles_doc))
            with self.assertRaisesRegex(
                producer.ProducerError, "missing-explicit-device-package"
            ):
                producer.write_package_intent(root, config, manifest_dir)

            profiles_doc["profiles"]["glinet_gl-axt1800"]["device_packages"].pop()
            profiles.write_text(json.dumps(profiles_doc))
            profiles_doc["profiles"]["glinet_gl-axt1800"]["device_packages"].append(
                "base-internal"
            )
            profiles.write_text(json.dumps(profiles_doc))
            with self.assertRaisesRegex(producer.ProducerError, "base-internal"):
                producer.write_package_intent(root, config, manifest_dir)
            profiles_doc["profiles"]["glinet_gl-axt1800"]["device_packages"].pop()
            profiles.write_text(json.dumps(profiles_doc))
            original_config = config.read_text()
            for selector in (
                "missing-config-package",
                "-missing-exclusion",
                "base-internal",
            ):
                with self.subTest(selector=selector):
                    config.write_text(
                        original_config.replace(
                            '"luci-app-a -luci-app-default"',
                            f'"luci-app-a {selector}"',
                        )
                    )
                    with self.assertRaisesRegex(
                        producer.ProducerError, selector.lstrip("-")
                    ):
                        producer.write_package_intent(root, config, manifest_dir)

    def test_package_intent_uses_staged_openwrt_apks_and_abi_names(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            ib = root / "imagebuilder"
            source = root / "source"
            (source / "bin").mkdir(parents=True)
            config = source / ".config"
            config.write_text(
                (ib / ".config").read_text()
                + 'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800="libcurl libubus liblua5.4 libnghttp2 kmod-hwmon-pwmfan"\n'
                + 'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_jdcloud_re-cs-02="libcurl libubus liblua5.4 libnghttp2"\n'
                + "CONFIG_PACKAGE_source-only=y\n"
            )
            packages = (
                ("ipq-wifi-glinet_gl-axt1800", "ipq-wifi-glinet_gl-axt1800", "2026.05.18~e20f4c6f-r1", ""),
                ("kmod-hwmon-pwmfan", "kmod-hwmon-pwmfan", "6.12.112-r1", ""),
                ("libcurl", "libcurl4", "8.22.0-r1", "4"),
                ("libubus", "libubus20251202", "2026.06.28~24864e78-r2", "20251202"),
                ("liblua5.4", "liblua5.4-5.4", "5.4.8-r1", "-5.4"),
                ("libnghttp2", "libnghttp2-14", "1.69.0-r1", "-14"),
            )
            packageinfo = ib / ".packageinfo"
            metadata = packageinfo.read_text() + "Package: source-only\n"
            staged = []
            for selector, name, version, suffix in packages:
                metadata += f"Package: {selector}\n"
                if selector == "libubus":
                    metadata += "Version: 2026.06.28~24864e7840b3a02a9ef76284a373f6b2f00b8a9b-r2\n"
                if selector == "kmod-hwmon-pwmfan":
                    metadata += "ABI-Version: 6.12.112-1\n"
                row = (name, version, "aarch64_cortex-a53")
                if suffix:
                    metadata += f"ABI-Version: {suffix.lstrip('-')}\n"
                    row += (selector, suffix)
                staged.append(row)
            self._stage_fixture_apks(ib, staged)
            packageinfo.write_text(metadata)
            (source / "bin/source-only_1_aarch64_cortex-a53.apk").write_bytes(b"apk")
            profiles_path = ib / "profiles.json"
            profiles = json.loads(profiles_path.read_text())
            profiles["profiles"]["glinet_gl-axt1800"]["device_packages"].append(packages[0][0])
            profiles_path.write_text(json.dumps(profiles))
            for profile in producer.REQUIRED_PROFILES:
                manifest = root / f"producer-manifests/openwrt-{profile}.manifest"
                manifest.write_text(
                    manifest.read_text()
                    + "".join(f"{name} - {version}\n" for _, name, version, _ in packages)
                )

            intent = producer.write_package_intent(root, config, root / "producer-manifests")
            expected = {
                profile: {row["name"]: row["version"] for row in record["expected"]}
                for profile, record in intent["profiles"].items()
            }
            self.assertNotIn("source-only", expected["glinet_gl-axt1800"])
            for profile in producer.REQUIRED_PROFILES:
                for selector, name, version, _ in packages:
                    if profile == "glinet_gl-axt1800" or selector.startswith("lib"):
                        self.assertEqual(expected[profile][name], version)

            for name, content in (
                ("source.config", config.read_text()),
                ("packageinfo", metadata),
                ("profiles.json", profiles_path.read_text()),
            ):
                (root / "metadata" / name).write_text(content)
            (ib / "staging_dir/host/bin/apk").chmod(0o644)
            producer.write_manifest(root, PROVENANCE)
            self.assertEqual(producer.validate_bundle(root)["apk_count"], len(packages) + 2)

            (ib / "staging_dir/host/bin/apk").chmod(0o755)
            config.write_text(config.read_text().replace('libcurl libubus', '-libcurl libubus', 1))
            (root / "metadata/source.config").write_text(config.read_text())
            manifest = root / "producer-manifests/openwrt-glinet_gl-axt1800.manifest"
            manifest.write_text(manifest.read_text().replace("libcurl4 - 8.22.0-r1\n", ""))
            intent = producer.write_package_intent(root, config, root / "producer-manifests")
            profile = intent["profiles"]["glinet_gl-axt1800"]
            self.assertEqual(profile["excluded"], ["libcurl", "libcurl4"])
            self.assertNotIn("libcurl4", {row["name"] for row in profile["expected"]})
            producer.write_manifest(root, PROVENANCE)
            producer.validate_bundle(root)

    def test_explicit_device_apk_requires_matching_arch_and_archived_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            ib = root / "imagebuilder"
            config = root / "metadata/source.config"
            manifests = root / "producer-manifests"
            pool = ib / "packages"
            target = "kmod-example-1.apk"
            index = pool / "packages.adb"
            index.write_text(index.read_text().replace(
                "kmod-example\n    version: 1\n    arch: aarch64_cortex-a53",
                "kmod-example\n    version: 1\n    arch: x86_64",
            ))
            with self.assertRaisesRegex(producer.ProducerError, "matching-ABI APK pool.*kmod-example"):
                producer.write_package_intent(root, config, manifests)

            self._stage_fixture_apks(ib, [("kmod-unused", "1", "aarch64_cortex-a53")])
            profiles = ib / "profiles.json"
            original = profiles.read_text()
            doc = json.loads(original)
            for profile in doc["profiles"].values():
                profile["device_packages"].remove("kmod-example")
            profiles.write_text(json.dumps(doc))
            producer.write_package_intent(root, config, manifests)
            profiles.write_text(original)
            intent_path = root / "metadata/package-intent.json"
            intent = json.loads(intent_path.read_text())
            intent["profiles"]["glinet_gl-axt1800"]["expected"].append(
                {"name": "kmod-example", "version": "1"}
            )
            intent_path.write_text(json.dumps(intent))
            producer.write_manifest(root, PROVENANCE)
            with self.assertRaisesRegex(producer.ProducerError, "matching-ABI APK pool"):
                producer.validate_bundle(root)

            source_pool = root / "metadata/bin"
            source_pool.mkdir()
            (pool / target).rename(source_pool / target)
            for state in ("missing", "empty", "symlink"):
                with self.subTest(state=state):
                    if state == "empty":
                        (pool / target).touch()
                    elif state == "symlink":
                        (pool / target).symlink_to(source_pool / target)
                    with self.assertRaisesRegex(producer.ProducerError, re.escape(target)):
                        producer.write_package_intent(root, config, manifests)
                    producer.write_manifest(root, PROVENANCE)
                    with self.assertRaisesRegex(producer.ProducerError, re.escape(target)):
                        producer.validate_bundle(root)
                    (pool / target).unlink(missing_ok=True)

    def test_apk_catalog_rejects_resealed_index_and_package_changes(self):
        for relative, update, expected in (
            ("packages.adb", lambda content: content + b"# replacement\n", "catalog does not match"),
            ("base-files-1.apk", lambda content: b"bad", "indexed APK does not match"),
            ("unindexed-1.apk", lambda content: b"apk", "absent from packages.adb"),
        ):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self._make_bundle(root)
                path = root / "imagebuilder/packages" / relative
                path.write_bytes(update(path.read_bytes() if path.exists() else b""))
                producer.write_manifest(root, PROVENANCE)
                with self.assertRaisesRegex(producer.ProducerError, expected):
                    producer.validate_bundle(root)
                if relative == "unindexed-1.apk":
                    with self.assertRaisesRegex(producer.ProducerError, expected):
                        producer.write_package_intent(
                            root, root / "metadata/source.config", root / "producer-manifests"
                        )

    def test_package_intent_requires_exact_manifest_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            manifests = root / "producer-manifests"
            (manifests / "openwrt-glinet_gl-axt1800.manifest").write_text(
                "base-files - 2\nkmod-example - 1\n"
            )
            with self.assertRaisesRegex(producer.ProducerError, "matching-ABI APK pool.*base-files"):
                producer.write_package_intent(root, root / "metadata/source.config", manifests)

    def test_explicit_exclusion_overrides_common_package_in_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            config = root / "metadata/source.config"
            config.write_text(
                config.read_text() + "CONFIG_PACKAGE_base-files=y\n"
                'CONFIG_TARGET_DEVICE_PACKAGES_qualcommax_ipq60xx_DEVICE_glinet_gl-axt1800="-base-files"\n'
            )
            manifests = root / "producer-manifests"
            (manifests / "openwrt-glinet_gl-axt1800.manifest").write_text("kmod-example - 1\n")
            intent = producer.write_package_intent(root, config, manifests)
            self.assertEqual(intent["common"], [{"name": "base-files", "version": "1"}])
            self.assertEqual(intent["profiles"]["glinet_gl-axt1800"]["excluded"], ["base-files"])
            producer.write_manifest(root, PROVENANCE)
            producer.validate_bundle(root)

    def test_package_intent_ignores_manifest_runtime_dependencies_missing_from_packageinfo(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            manifest_dir = root / "producer-manifests"
            runtime_dependencies = (
                "libcurl4 - 8.10.1\n"
                "libubus20251202 - 2025.12.02\n"
                "kernel - 6.12.1\n"
            )
            for profile_name in producer.REQUIRED_PROFILES:
                path = manifest_dir / f"openwrt-{profile_name}.manifest"
                path.write_text(path.read_text() + runtime_dependencies)

            producer.write_package_intent(
                root, root / "imagebuilder/.config", manifest_dir,
            )
            producer.write_manifest(root, PROVENANCE)

            intent = json.loads((root / "metadata/package-intent.json").read_text())
            expected_names = {
                record["name"]
                for profile in intent["profiles"].values()
                for record in profile["expected"]
            }
            self.assertEqual(expected_names, {"base-files", "kmod-example"})
            for profile_name in producer.REQUIRED_PROFILES:
                evidence = (
                    root / f"metadata/manifests/{profile_name}.manifest"
                ).read_text()
                self.assertIn("libcurl4 - 8.10.1", evidence)
                self.assertIn("libubus20251202 - 2025.12.02", evidence)
                self.assertIn("kernel - 6.12.1", evidence)

            result = producer.validate_bundle(root)
            self.assertEqual(result["profiles"], list(producer.REQUIRED_PROFILES))

    def test_stage_recovery_requires_matching_source_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            bundle = root / "bundle"
            source.mkdir()
            bundle.mkdir()
            lines = []
            for profile_name, contract in producer._image_contract().items():
                for image_name in contract["producer_fallback"]:
                    contents = ("producer:" + profile_name).encode()
                    (source / image_name).write_bytes(contents)
                    lines.append(
                        f"{hashlib.sha256(contents).hexdigest()}  {image_name}\n"
                    )
            (source / "sha256sums").write_text("".join(lines))

            result = producer.stage_recovery_images(source, bundle)

            self.assertEqual(set(result), set(producer.REQUIRED_PROFILES))
            self.assertTrue((bundle / "recovery/images.json").is_file())
            for profile_name, contract in producer._image_contract().items():
                image_name = contract["producer_fallback"][0]
                self.assertTrue(
                    (bundle / "recovery" / profile_name / image_name).is_file()
                )

            (source / "sha256sums").write_text("0" * 64 + "  " + lines[0].split("  ", 1)[1])
            with self.assertRaisesRegex(producer.ProducerError, "checksum"):
                producer.stage_recovery_images(source, bundle)

    def test_bundle_validation_requires_selected_apks_for_package_intent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            packageinfo = root / "imagebuilder/.packageinfo"
            packageinfo.write_text(packageinfo.read_text() + "Package: missing-common\n")
            (root / "metadata/packageinfo").write_text(packageinfo.read_text())
            intent = {
                "schema": 1,
                "common": [{"name": "base-files", "version": "1"}],
                "profiles": {
                    "glinet_gl-axt1800": {
                        "packages": [{"name": "missing-common", "version": "1"}],
                        "expected": [
                            {"name": "base-files", "version": "1"},
                            {"name": "kmod-example", "version": "1"},
                            {"name": "missing-common", "version": "1"},
                        ],
                        "excluded": [],
                    },
                    "jdcloud_re-cs-02": {
                        "packages": [{"name": "kmod-example", "version": "1"}],
                        "expected": [
                            {"name": "base-files", "version": "1"},
                            {"name": "kmod-example", "version": "1"},
                        ],
                        "excluded": [],
                    },
                },
            }
            (root / "metadata/package-intent.json").write_text(json.dumps(intent))
            (root / "metadata/manifests/glinet_gl-axt1800.manifest").write_text(
                "base-files - 1\nkmod-example - 1\nmissing-common - 1\n"
            )
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "missing-common"):
                producer.validate_bundle(root)

    def test_rejects_missing_public_key_when_signature_check_is_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            for key in (root / "imagebuilder/keys").iterdir():
                key.unlink()
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "public.*key"):
                producer.validate_bundle(root)

    def test_rejects_remote_repository_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            (root / "imagebuilder/repositories").write_text(
                "https://downloads.example.invalid/packages.adb\n"
            )
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "remote repository"):
                producer.validate_bundle(root)

    def test_rejects_bundle_path_traversal_and_unhashed_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            sums = root / "SHA256SUMS"
            sums.write_text(sums.read_text() + "0" * 64 + "  ../outside\n")

            with self.assertRaisesRegex(producer.ProducerError, "unsafe path"):
                producer.validate_bundle(root)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            (root / "unexpected.apk").write_bytes(b"unhashed")

            with self.assertRaisesRegex(producer.ProducerError, "hash manifest"):
                producer.validate_bundle(root)

    def test_rejects_payload_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            with (
                root
                / "imagebuilder/packages/base-files-1.apk"
            ).open("ab") as f:
                f.write(b"tampered")

            with self.assertRaisesRegex(producer.ProducerError, "hash mismatch"):
                producer.validate_bundle(root)

    def test_rejects_private_signing_key_in_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)
            (root / "imagebuilder/keys/local-private-key.pem").write_text(
                "-----BEGIN PRIVATE KEY-----\nsecret\n"
            )
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "private key"):
                producer.validate_bundle(root)


if __name__ == "__main__":
    unittest.main()
