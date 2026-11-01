import unittest
from partitioning import evaluate_partition


class TestPartitioning(unittest.TestCase):
    def test_balanced_beats_unbalanced(self):
        balanced = evaluate_partition(["0"] * 4 + ["1"] * 4)
        unbalanced = evaluate_partition(["0"] * 7 + ["1"])
        self.assertGreater(balanced["entropy"], unbalanced["entropy"])
        self.assertEqual(balanced["worst_case_eliminated"], 4)
        self.assertEqual(unbalanced["worst_case_eliminated"], 1)

    def test_multi_output_classes(self):
        score = evaluate_partition(["00", "01", "10", "11"])
        self.assertEqual(score["num_classes"], 4)
        self.assertAlmostEqual(score["entropy"], 2.0)


if __name__ == "__main__":
    unittest.main()
