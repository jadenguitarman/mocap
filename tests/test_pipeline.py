import csv
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.abspath("src"))

sys.modules.setdefault("cv2", types.SimpleNamespace(Rodrigues=lambda rvec: (None, None)))
sys.modules.setdefault("librosa", types.SimpleNamespace())
sys.modules.setdefault(
    "capture.audio",
    types.SimpleNamespace(AudioRecorder=types.SimpleNamespace(find_sync_spike=lambda filename: None)),
)
sys.modules.setdefault("toml", types.SimpleNamespace(load=lambda path: {}))

from processing.pipeline import MocapPipeline


class PipelineTests(unittest.TestCase):
    def test_extract_mobile_device_id_keeps_underscores_in_id(self):
        device_id = MocapPipeline.extract_mobile_device_id(
            "Scene_01_001_phone_alpha_987654.webm",
            "Scene_01",
            "001",
        )

        self.assertEqual(device_id, "phone_alpha")

    def test_verify_csv_requires_header_and_data_row(self):
        tmp = os.path.abspath(os.path.join("tests", "_tmp_pipeline"))
        os.makedirs(tmp, exist_ok=True)
        path = os.path.join(tmp, "take.csv")
        pipeline = MocapPipeline(openpose_path="missing.exe", output_dir=tmp)
        header = ["Time"] + [f"Bone_{i}_{axis}" for i in range(25) for axis in ["X", "Y", "Z"]]
        row = [0.0] + [0.0] * 75
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerow(row)

        self.assertTrue(pipeline.verify_csv(path))


if __name__ == "__main__":
    unittest.main()
