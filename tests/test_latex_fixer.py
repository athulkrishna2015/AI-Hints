import sys
import os

# Add the project root and addon directory to sys.path
root_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(root_dir)
sys.path.append(os.path.join(root_dir, "addon"))

from latex_fixer import fix_latex

def test_latex_fixer():
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
        
        # Over-escaped delimiters (common in JSON)
        ("\\\\( x \\\\)", "\\( x \\)"),
        
        # Mixed content
        ("The slope (m) is delta_y / delta_x.", "The slope (m) is \\(\\Delta_y / \\Delta_x\\)."), # Note: Case sensitivity check
        ("Here is lambda: lambda_0.", "Here is \\(\\lambda\\): \\(\\lambda_0\\)."),
    ]

    print("Running LaTeX Fixer Tests...")
    passed = 0
    for i, (input_text, expected) in enumerate(test_cases):
        actual = fix_latex(input_text)
        # Note: Delta is case-insensitive in my regex list? Let's check the regex.
        # It's actually lowercase 'delta' in the list.
        if actual == expected:
            print(f"Test {i+1}: PASSED")
            passed += 1
        else:
            print(f"Test {i+1}: FAILED")
            print(f"  Input:    {input_text}")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")

    print(f"\nSummary: {passed}/{len(test_cases)} tests passed.")

if __name__ == "__main__":
    test_latex_fixer()
