import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))

from processing.filter import MocapFilter


class FilterTests(unittest.TestCase):
    def test_missing_points_are_replaced_with_zeroes(self):
        filt = MocapFilter(num_points=2)

        result = filt.filter_frame(0.0, [[1.0, 2.0, 3.0], None])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[1], [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
