import os
import sys
import types
import unittest

sys.path.insert(0, os.path.abspath("src"))

cv2_stub = types.SimpleNamespace(
    VideoCapture=lambda *args, **kwargs: None,
    CAP_PROP_FRAME_WIDTH=3,
    CAP_PROP_FRAME_HEIGHT=4,
    imshow=lambda *args, **kwargs: None,
    waitKey=lambda *args, **kwargs: -1,
    destroyAllWindows=lambda: None,
)
sys.modules.setdefault("cv2", cv2_stub)

aruco_stub = types.SimpleNamespace()
cv2_stub.aruco = aruco_stub
sys.modules.setdefault("cv2.aruco", aruco_stub)
sys.modules.setdefault("requests", types.SimpleNamespace(post=lambda *args, **kwargs: None))
sys.modules.setdefault("toml", types.SimpleNamespace(load=lambda path: {}))

from calibrate_cli import calibration_complete_ids


class CalibrationTests(unittest.TestCase):
    def test_complete_ids_require_intrinsics_and_extrinsics(self):
        data = {
            "mtx_cam0": object(),
            "dist_cam0": object(),
            "rvec_cam0": object(),
            "tvec_cam0": object(),
            "mtx_cam1": object(),
            "dist_cam1": object(),
        }

        self.assertEqual(calibration_complete_ids(data), ["cam0"])


if __name__ == "__main__":
    unittest.main()
