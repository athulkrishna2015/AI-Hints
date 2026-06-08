import re
import sys

def check_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Simple depth tracker
    depth = 0
    in_string = None
    escaped = False

    for i, char in enumerate(content):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue

        if in_string:
            if char == in_string:
                in_string = None
            continue

        if char in ("\"", "\'"):
            in_string = char
            continue

        if char == "#":
            # Skip till newline
            while i < len(content) and content[i] != "\n":
                i += 1
            continue

        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                line_no = content.count("\n", 0, i) + 1
                print(f"Unmatched ) at line {line_no}")
                depth = 0 # reset

    if depth != 0:
        print(f"Final depth is {depth}")

if __name__ == "__main__":
    check_file(sys.argv[1])
