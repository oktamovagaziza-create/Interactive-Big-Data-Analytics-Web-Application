from pathlib import Path
import unittest

import pandas as pd

from app.analyzer import analyze_dataframe, parse_dataset


ROOT = Path(__file__).resolve().parents[1]


class AnalyzerTests(unittest.TestCase):
    def test_analyze_sample_dataset_generates_expected_sections(self):
        df = pd.read_csv(ROOT / "samples" / "car_sales.csv")
        result = analyze_dataframe(df, filename="car_sales.csv")

        self.assertEqual(result["summary"]["cleaned_shape"][0], len(df))
        self.assertTrue(result["summary"]["column_types"]["numeric"])
        self.assertTrue(result["visualizations"])
        self.assertTrue(result["statistics"]["top_correlations"])
        self.assertTrue(result["insights"])
        self.assertIn("Recommendation", result["conclusions"])

    def test_parser_rejects_wrong_format(self):
        with self.assertRaisesRegex(ValueError, "CSV or Excel"):
            parse_dataset("notes.txt", b"hello")


if __name__ == "__main__":
    unittest.main()
