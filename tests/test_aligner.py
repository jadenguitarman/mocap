import os
import sys
import types
import unittest

sys.path.insert(0, os.path.abspath("src"))

librosa_stub = types.SimpleNamespace(
    load=lambda *args, **kwargs: ([], 1),
    get_duration=lambda path: 0.0,
    onset=types.SimpleNamespace(onset_detect=lambda **kwargs: []),
    frames_to_time=lambda frames, sr: [],
)
sys.modules.setdefault("librosa", librosa_stub)

from processing.aligner import AudioAligner


class AudioAlignerTests(unittest.TestCase):
    def test_two_sync_onsets_drive_drift(self):
        aligner = AudioAligner()

        drift = aligner.get_drift(
            ref_onsets=[2.0, 12.0],
            mob_onsets=[1.0, 11.2],
        )

        self.assertAlmostEqual(drift, 10.0 / 10.2)

    def test_implausible_drift_is_rejected(self):
        aligner = AudioAligner()

        drift = aligner.get_drift(
            ref_onsets=[2.0, 12.0],
            mob_onsets=[1.0, 5.0],
        )

        self.assertEqual(drift, 1.0)

    def test_calculate_offsets_uses_basename(self):
        aligner = AudioAligner()
        aligner.find_onsets = lambda path: [2.0, 12.0] if path == "pc.wav" else [1.5, 11.5]

        offsets = aligner.calculate_offsets("pc.wav", [r"uploads\Scene_01_001_phone-a_123.webm"])

        key = os.path.basename(r"uploads\Scene_01_001_phone-a_123.webm")
        self.assertIn(key, offsets)
        self.assertAlmostEqual(offsets[key]["time_offset"], 0.5)
        self.assertAlmostEqual(offsets[key]["drift_factor"], 1.0)

    def test_single_sync_point_refuses_alignment(self):
        aligner = AudioAligner()
        aligner.find_onsets = lambda path: [2.0]

        offsets = aligner.calculate_offsets("pc.wav", ["phone.webm"])

        self.assertEqual(offsets, {})


if __name__ == "__main__":
    unittest.main()
