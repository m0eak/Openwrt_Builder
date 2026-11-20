#!/usr/bin/env python3
"""Offline structure and fixture checks for the IPQ consumer validation workflow."""

from __future__ import annotations

import json
import importlib.util
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by environments without PyYAML
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/Validate IPQ ImageBuilder Consumer.yml"
PRODUCER_WORKFLOW = ROOT / ".github/workflows/Validate IPQ ImageBuilder Producer.yml"
REUSABLE_WORKFLOW = ROOT / ".github/workflows/_openwrt-build-device.yml"
PROFILES = ("glinet_gl-axt1800", "jdcloud_re-cs-02")
_consumer_spec = importlib.util.spec_from_file_location(
    "ipq_imagebuilder_consumer", ROOT / "sh" / "ipq-imagebuilder-consumer.py"
)
consumer = importlib.util.module_from_spec(_consumer_spec)
_consumer_spec.loader.exec_module(consumer)


def _events(document):
    return document.get("on", document.get(True, {}))


class ConsumerWorkflowStructureTests(unittest.TestCase):
    def setUp(self):
        if yaml is None:
            self.skipTest("pyyaml not available")
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def test_workflow_is_manual_and_isolated(self):
        self.assertEqual(set(_events(self.workflow)), {"workflow_dispatch"})
        jobs = self.workflow["jobs"]
        self.assertEqual(set(jobs), {"consumer"})
        consumer = jobs["consumer"]
        self.assertEqual(
            consumer["strategy"]["matrix"]["profile"],
            list(PROFILES),
        )
        self.assertNotIn("publish", str(jobs).lower())
        self.assertNotIn("release", str(jobs).lower())

        inputs = _events(self.workflow)["workflow_dispatch"]["inputs"]
        self.assertTrue(inputs["producer_run_id"]["required"])
        self.assertNotIn("producer_run_attempt", inputs)
        self.assertEqual(
            self.workflow["permissions"],
            {"actions": "read", "contents": "read"},
        )

    def test_download_uses_producer_artifact_contract(self):
        steps = self.workflow["jobs"]["consumer"]["steps"]
        download = next(
            step
            for step in steps
            if step.get("name") == "Download producer ImageBuilder artifact"
        )
        self.assertEqual(download["uses"], "actions/download-artifact@main")
        with_args = download["with"]
        self.assertEqual(
            with_args["name"],
            "ipq-imagebuilder-producer-${{ inputs.producer_run_id }}",
        )
        self.assertEqual(with_args["run-id"], "${{ inputs.producer_run_id }}")
        self.assertEqual(with_args["repository"], "${{ github.repository }}")
        self.assertEqual(with_args["github-token"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertEqual(
            with_args["path"], "${{ runner.temp }}/ipq-imagebuilder-producer"
        )

        producer = yaml.safe_load(PRODUCER_WORKFLOW.read_text(encoding="utf-8"))
        reusable = yaml.safe_load(REUSABLE_WORKFLOW.read_text(encoding="utf-8"))
        upload_steps = [
            step
            for step in reusable["jobs"]["build"]["steps"]
            if step.get("name") == "Upload IPQ ImageBuilder producer artifact"
        ]
        self.assertEqual(len(upload_steps), 1)
        self.assertEqual(
            upload_steps[0]["with"]["name"],
            "ipq-imagebuilder-producer-${{ github.run_id }}",
        )
        self.assertEqual(upload_steps[0]["with"]["include-hidden-files"], True)
        self.assertEqual(upload_steps[0]["with"]["overwrite"], True)
        self.assertEqual(
            producer["jobs"]["producer"]["with"]["producer_validation"], True
        )

    def test_both_profiles_run_manifest_then_image(self):
        job = self.workflow["jobs"]["consumer"]
        steps = job["steps"]
        build_step = next(
            step for step in steps if step.get("name") == "Build and verify ImageBuilder consumer"
        )
        run = build_step["run"]
        self.assertEqual(build_step["env"]["PROFILE"], "${{ matrix.profile }}")
        self.assertIn('make manifest "PROFILE=$PROFILE" "PACKAGES=$PACKAGE_ARGS"', run)
        self.assertIn('make image "PROFILE=$PROFILE" "PACKAGES=$PACKAGE_ARGS"', run)
        self.assertIn("package-args", run)
        self.assertIn("restore-recovery-images", run)
        self.assertLess(
            run.index('make manifest "PROFILE=$PROFILE"'),
            run.index('make image "PROFILE=$PROFILE"'),
        )
        self.assertIn("imagebuilder.tar.zst", run)
        self.assertIn("--strip-components=1", run)
        self.assertIn('test -d "$WORKDIR/bin/targets/qualcommax/ipq60xx"', run)
        self.assertIn('ipq-imagebuilder-consumer.py" verify', run)
        self.assertIn('--profile "$PROFILE"', run)
        for profile in PROFILES:
            self.assertIn(profile, job["strategy"]["matrix"]["profile"])

        steps_by_name = {step.get("name"): step for step in steps}
        validation = next(
            step["run"]
            for step in steps
            if step.get("name") == "Validate producer bundle and provenance"
        )
        self.assertIn("ipq-imagebuilder-producer.py validate", validation)
        self.assertIn("provenance.json", validation)
        self.assertIn("SHA256SUMS", validation)
        self.assertIn("metadata/package-intent.json", validation)
        self.assertLess(
            list(steps_by_name).index("Validate producer bundle and provenance"),
            list(steps_by_name).index("Build and verify ImageBuilder consumer"),
        )

        for step in steps:
            if "run" in step:
                self.assertNotIn("secrets.GITHUB_TOKEN", step["run"])
                self.assertNotIn("artifact_url", step["run"].lower())


class ConsumerFixtureTests(unittest.TestCase):
    def _write_output_fixture(self, root: Path, profile: str):
        workdir = root / profile
        output_dir = workdir / "bin/targets/qualcommax/ipq60xx"
        output_dir.mkdir(parents=True)
        images = {
            f"openwrt-qualcommax-ipq60xx-{profile}-sysupgrade.bin": {
                "name": f"openwrt-qualcommax-ipq60xx-{profile}-sysupgrade.bin"
            }
        }
        (output_dir / "profiles.json").write_text(
            json.dumps(
                {
                    "profiles": {
                        profile: {
                            "image_prefix": f"openwrt-qualcommax-ipq60xx-{profile}",
                            "images": list(images.values()),
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        image_name = next(iter(images))
        (
            output_dir / f"openwrt-qualcommax-ipq60xx-{profile}.manifest"
        ).write_text(
            "base-files\n", encoding="utf-8"
        )
        (output_dir / image_name).write_bytes(b"firmware")
        required_images = consumer.REQUIRED_IMAGES[profile]
        sums = []
        for required_name in required_images:
            contents = f"required:{required_name}".encode()
            (output_dir / required_name).write_bytes(contents)
            sums.append(
                f"{hashlib.sha256(contents).hexdigest()}  {required_name}\n"
            )
        (output_dir / "sha256sums").write_text("".join(sums), encoding="utf-8")
        return workdir, image_name

    def test_verify_outputs_accepts_manifest_and_declared_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for profile in PROFILES:
                workdir, image_name = self._write_output_fixture(root, profile)
                result = consumer.verify_outputs(workdir, profile)
                self.assertEqual(result["profile"], profile)
                self.assertEqual(result["images"], [image_name])

    def test_verify_outputs_rejects_missing_declared_image(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir, image_name = self._write_output_fixture(
                root, "glinet_gl-axt1800"
            )
            (
                workdir / "bin/targets/qualcommax/ipq60xx" / image_name
            ).unlink()
            with self.assertRaisesRegex(consumer.ConsumerError, "missing image output"):
                consumer.verify_outputs(workdir, "glinet_gl-axt1800")

    def test_verify_outputs_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir, _ = self._write_output_fixture(root, "jdcloud_re-cs-02")
            next(
                (workdir / "bin/targets/qualcommax/ipq60xx").glob("*.manifest")
            ).unlink()
            with self.assertRaisesRegex(consumer.ConsumerError, "exactly one"):
                consumer.verify_outputs(workdir, "jdcloud_re-cs-02")

    def test_verify_outputs_requires_fixed_images_independent_of_profiles_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir, _ = self._write_output_fixture(root, "glinet_gl-axt1800")
            output_dir = workdir / "bin/targets/qualcommax/ipq60xx"
            missing = consumer.REQUIRED_IMAGES["glinet_gl-axt1800"][0]
            (output_dir / missing).unlink()
            with self.assertRaisesRegex(consumer.ConsumerError, "required image"):
                consumer.verify_outputs(workdir, "glinet_gl-axt1800")

    def test_verify_outputs_checks_published_image_checksums(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir, _ = self._write_output_fixture(root, "jdcloud_re-cs-02")
            output_dir = workdir / "bin/targets/qualcommax/ipq60xx"
            with (output_dir / "sha256sums").open("a") as stream:
                stream.write(f"{'0' * 64}  {consumer.REQUIRED_IMAGES['jdcloud_re-cs-02'][0]}\n")
            with self.assertRaisesRegex(consumer.ConsumerError, "checksum"):
                consumer.verify_outputs(workdir, "jdcloud_re-cs-02")

    def test_restore_uses_only_profile_scoped_producer_recovery_image(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            profile = "glinet_gl-axt1800"
            workdir, _ = self._write_output_fixture(root, profile)
            output_dir = workdir / "bin/targets/qualcommax/ipq60xx"
            fallback = consumer.PRODUCER_FALLBACK_IMAGES[profile][0]
            (output_dir / fallback).unlink()
            bundle = root / "bundle"
            recovery = bundle / "recovery" / profile
            recovery.mkdir(parents=True)
            contents = b"producer image for AXT only"
            (recovery / fallback).write_bytes(contents)
            (bundle / "recovery" / "images.json").write_text(
                json.dumps(
                    {
                        profile: {
                            fallback: {
                                "path": f"recovery/{profile}/{fallback}",
                                "sha256": hashlib.sha256(contents).hexdigest(),
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (bundle / "SHA256SUMS").write_text(
                f"{hashlib.sha256(contents).hexdigest()}  recovery/{profile}/{fallback}\n",
                encoding="utf-8",
            )

            consumer.restore_recovery_images(bundle, workdir, profile)
            result = consumer.verify_outputs(workdir, profile)

            self.assertEqual((output_dir / fallback).read_bytes(), contents)
            self.assertIn(fallback, result["required_images"])
            with self.assertRaisesRegex(consumer.ConsumerError, "recovery image"):
                consumer.restore_recovery_images(bundle, workdir, "jdcloud_re-cs-02")

    def test_verify_outputs_accepts_root_profiles_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workdir, _ = self._write_output_fixture(root, "glinet_gl-axt1800")
            output_dir = workdir / "bin/targets/qualcommax/ipq60xx"
            profiles = output_dir / "profiles.json"
            (workdir / "profiles.json").write_bytes(profiles.read_bytes())
            profiles.unlink()
            result = consumer.verify_outputs(workdir, "glinet_gl-axt1800")
            self.assertEqual(result["profile"], "glinet_gl-axt1800")

    def test_profile_commands_run_against_each_extracted_fixture(self):
        """Exercise the exact consumer command shape without a real ImageBuilder."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / "bundle"
            archive_root = root / "archive-root" / "imagebuilder"
            archive_root.mkdir(parents=True)
            (archive_root / "Makefile").write_text(
                "manifest:\n"
                "\t@printf 'manifest %s\\n' '$(PROFILE)' >> commands.log\n"
                "image:\n"
                "\t@printf 'image %s\\n' '$(PROFILE)' >> commands.log\n",
                encoding="utf-8",
            )
            (bundle / "imagebuilder.tar.zst").parent.mkdir()
            shutil.copy2(archive_root / "Makefile", bundle / "fixture-Makefile")

            # The workflow uses tar --zstd; mock tar only for this offline fixture.
            fakebin = root / "bin"
            fakebin.mkdir()
            tar = fakebin / "tar"
            tar.write_text(
                "#!/bin/sh\n"
                "set -eu\n"
                "dest=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    -C) dest=$2; shift 2;;\n"
                "    *) shift;;\n"
                "  esac\n"
                "done\n"
                "cp \"$FIXTURE_MAKEFILE\" \"$dest/Makefile\"\n",
                encoding="utf-8",
            )
            tar.chmod(0o755)

            for profile in PROFILES:
                workdir = root / f"imagebuilder-{profile}"
                workdir.mkdir()
                env = {
                    **os.environ,
                    "FIXTURE_MAKEFILE": str(archive_root / "Makefile"),
                    "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
                }
                commands = (
                    "set -euo pipefail\n"
                    f'tar --zstd -xf "{bundle}/imagebuilder.tar.zst" '
                    f'-C "{workdir}" --strip-components=1\n'
                    f'cd "{workdir}"\n'
                    f"make manifest PROFILE={profile}\n"
                    f"make image PROFILE={profile}\n"
                )
                result = subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", commands],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(
                    (workdir / "commands.log").read_text(encoding="utf-8").splitlines(),
                    [f"manifest {profile}", f"image {profile}"],
                )


if __name__ == "__main__":
    unittest.main()
