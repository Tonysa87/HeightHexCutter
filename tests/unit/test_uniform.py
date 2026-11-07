"""Uniformity test on channel arrays (pure numpy)."""
import unittest

import numpy as np

from height_hex_cutter.uniform import uniform_value


class TestUniform(unittest.TestCase):
    def test_all_equal(self):
        self.assertAlmostEqual(uniform_value(np.full(100, 0.25, np.float32)), 0.25, places=6)

    def test_small_noise_is_uniform(self):
        rng = np.random.default_rng(1)
        a = 0.5 + (rng.random(1000, dtype=np.float32) - 0.5) * (0.5 / 255)
        self.assertAlmostEqual(uniform_value(a), float(a.mean()), places=6)

    def test_one_pixel_off(self):
        a = np.zeros(1000, np.float32)
        a[17] = 2.0 / 255
        self.assertIsNone(uniform_value(a))

    def test_empty(self):
        self.assertIsNone(uniform_value(np.zeros(0, np.float32)))


if __name__ == "__main__":
    unittest.main()
