#!/usr/bin/env python3
"""Offline structure and fixture checks for the IPQ consumer validation workflow."""

from __future__ import annotations

import json
import importlib.util
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
        self.assertNotIn("strategy", consumer)
        self.assertNotIn("publish", str(jobs).lower())
        self.assertNotIn("release", str(jobs).lower())

        inputs = _events(self.workflow)["workflow_dispatch"]["inputs"]
        self.assertTrue(inputs["producer_run_id"]["required"])
        self.assertEqual(inputs["producer_run_attempt"]["default"], "1")
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
            "ipq-imagebuilder-producer-${{ inputs.producer_run_id }}-${{ inputs.producer_run_attempt }}",
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
            "ipq-imagebuilder-producer-${{ github.run_id }}-${{ github.run_attempt }}",
        )
        self.assertEqual(upload_steps[0]["with"]["include-hidden-files"], True)
        self.assertEqual(
            producer["jobs"]["producer"]["with"]["producer_validation"], True
        )

    def test_both_profiles_run_manifest_then_image(self):
        steps = self.workflow["jobs"]["consumer"]["steps"]
        profile_steps = {
            step["name"]: step["run"]
            for step in steps
            if step.get("name", "").startswith("Validate ")
            and "ImageBuilder consumer" in step.get("name", "")
        }
        self.assertEqual(len(profile_steps), 2)
        for profile in PROFILES:
            matching = [run for name, run in profile_steps.items() if profile in name]
            self.assertEqual(len(matching), 1)
            run = matching[0]
            manifest = f"make manifest PROFILE={profile}"
            image = f"make image PROFILE={profile}"
            self.assertIn(manifest, run)
            self.assertIn(image, run)
            self.assertLess(run.index(manifest), run.index(image))
            self.assertIn("imagebuilder.tar.zst", run)
            self.assertIn("--strip-components=1", run)
            self.assertIn(
                'test -d "$WORKDIR/bin/targets/qualcommax/ipq60xx"', run
            )

        validation = next(
            step["run"]
            for step in steps
            if step.get("name") == "Validate producer bundle and provenance"
        )
        self.assertIn("ipq-imagebuilder-producer.py validate", validation)
        self.assertIn("provenance.json", validation)
        self.assertIn("SHA256SUMS", validation)
        validation_index = next(
            index
            for index, step in enumerate(steps)
            if step.get("name") == "Validate producer bundle and provenance"
        )

        for profile in PROFILES:
            profile_index = next(
                index
                for index, step in enumerate(steps)
                if step.get("name") == f"Validate {profile} ImageBuilder consumer"
            )
            run = steps[profile_index]["run"]
            self.assertLess(validation_index, profile_index)
            self.assertIn('ipq-imagebuilder-consumer.py" verify', run)
            self.assertIn(f"--profile {profile}", run)
            self.assertIn("--workdir \"$WORKDIR\"", run)

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
