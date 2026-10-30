"""Ensure a saved script always exposes the next production stage."""
import ast
from pathlib import Path
import unittest


class NextNavigationTests(unittest.TestCase):
    def test_visual_bible_next_button_not_gated_by_review_result(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        root = ast.parse(source)
        parents = {
            child: parent
            for parent in ast.walk(root)
            for child in ast.iter_child_nodes(parent)
        }
        next_buttons = []
        for node in ast.walk(root):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "button":
                continue
            if any(
                kw.arg == "key"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "next_to_visual_bible"
                for kw in node.keywords
            ):
                next_buttons.append(node)

        self.assertEqual(len(next_buttons), 1, "There must be exactly one Next → Visual Bible button")
        ancestors = []
        node = next_buttons[0]
        while node in parents:
            node = parents[node]
            ancestors.append(node)
        conditions = [
            ast.unparse(ancestor.test)
            for ancestor in ancestors
            if isinstance(ancestor, ast.If)
        ]
        self.assertIn("not script", conditions, "Next must require a saved script")
        self.assertNotIn("passed", conditions, "Next must remain visible below the target")
        self.assertNotIn("critique", conditions, "Next must remain visible without a review")
        self.assertIn("Continue production", source)


if __name__ == "__main__":
    unittest.main()
