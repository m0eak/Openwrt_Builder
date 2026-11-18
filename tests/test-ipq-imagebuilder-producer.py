#!/usr/bin/env python3
import importlib.util
import json
import os
import re
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
        (ib / ".packageinfo").write_text("Package: base-files\n")
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
        (ib / "packages/base-files-1.apk").write_bytes(b"fixture apk")
        (ib / "packages/kmod-example-1.apk").write_bytes(b"fixture kmod")
        (ib / "packages/packages.adb").write_bytes(b"fixture ImageBuilder index")
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
            "kmod-example-1.apk").write_bytes(b"fixture kmod repository")
        (root / "repositories/packages/aarch64_cortex-a53/base/"
            "packages.adb").write_bytes(b"fixture feed index")
        (root / "repositories/packages/aarch64_cortex-a53/base/"
            "base-files-1.apk").write_bytes(b"fixture repository apk")
        producer.write_manifest(root, PROVENANCE)

    def test_valid_standalone_apk_bundle_has_complete_hash_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_bundle(root)

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
            package = root / "imagebuilder/packages/base-files-1.apk"
            package.unlink()
            profiles = root / "imagebuilder/profiles.json"
            profiles_doc = json.loads(profiles.read_text())
            profiles_doc["profiles"]["glinet_gl-axt1800"]["device_packages"].append(
                "missing-package"
            )
            profiles.write_text(json.dumps(profiles_doc))
            (root / "metadata/profiles.json").write_text(profiles.read_text())
            producer.write_manifest(root, PROVENANCE)

            with self.assertRaisesRegex(producer.ProducerError, "missing-package"):
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
            with (root / "imagebuilder/packages/base-files-1.apk").open("ab") as f:
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
