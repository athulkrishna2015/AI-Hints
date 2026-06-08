import sys
import os
import unittest

# Add the project root and addon directory to sys.path
sys.dont_write_bytecode = True
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)
sys.path.append(os.path.join(root_dir, "addon"))

from latex_fixer import fix_latex

class LatexFixerTests(unittest.TestCase):
    def test_latex_fixer_regressions(self):
        test_cases = [
            # Missing backslashes
            ("The value is lambda.", "The value is \\(\\lambda\\)."),
            ("Calculate frac{1}{2}.", "Calculate \\(\\frac{1}{2}\\)."),

            # Bare math tokens
            ("x_i + y_j = z_k", "\\(x_i + y_j = z_k\\)"),
            ("alpha_L is constant", "\\(\\alpha_L\\) is constant"),

            # Delimiter normalization
            ("$x+y$", "\\(x+y\\)"),
            ("$$x^2$$", "\\[x^2\\]"),

            # Over-escaped delimiters from JSON are normalized and trimmed.
            ("\\\\( x \\\\)", "\\(x\\)"),

            # Mixed content
            ("The slope (m) is delta_y / delta_x.", "The slope (m) is \\(\\delta_y / \\delta_x\\)."),
            ("Here is lambda: lambda_0.", "Here is \\(\\lambda\\): \\(\\lambda_0\\)."),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                self.assertEqual(fix_latex(input_text, fix_latex=True), expected)

if __name__ == "__main__":
    unittest.main()
