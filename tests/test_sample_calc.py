"""
Unit test for sample_calc.py.
"""

import sys
import unittest
sys.dont_write_bytecode = True

from sample_calc import calculate_discount

class TestSampleCalc(unittest.TestCase):
    def test_discount(self):
        # 10,000 - 2,000 should be 8,000
        self.assertEqual(calculate_discount(10000, 2000), 8000)

if __name__ == "__main__":
    unittest.main()
