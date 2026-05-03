import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath("src"))

from processing.triangulate import triangulate_frame


class TriangulateTests(unittest.TestCase):
    def test_missing_camera_points_do_not_crash(self):
        projections = [np.eye(3, 4), np.eye(3, 4)]
        keypoints = [
            [[100.0, 100.0, 0.9]],
            [],
        ]

        result = triangulate_frame(projections, keypoints)

        self.assertEqual(result, [None])


if __name__ == "__main__":
    unittest.main()
