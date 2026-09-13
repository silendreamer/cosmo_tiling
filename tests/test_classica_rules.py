import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from cosmo_tiling.converter import load_template
from cosmo_tiling.parsers.classica_columns import structured_rows
from cosmo_tiling.parsers.classica_rules import rules_for, validate_classica_rules

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/cosmo_tiling/config/templates/classica-template.json"
RULES = ROOT / "src/cosmo_tiling/config/rules/classica-rules.json"


def raw(text, heading=False, qty=""):
    return {"room": "ROOM", "type_description": text, "qty": qty,
            "selection_changed": "", "layout": {"is_heading": heading}}


class ClassicaRulesTests(unittest.TestCase):
    def test_corpus_waste_rules_use_literal_measured_quantity(self):
        cases = [
            ("3x6", "Herringbone", "Sample", 15),
            ("12x24", "Stacked Horizontal", "Sample", 22),
            ("8x48", "Offset", "Sample", 15),
            ("12x24", "Offset", "Sample", 12),
            ("3x12", "Stacked Vertical", "Sample", 10),
        ]
        for size, pattern, description, percent in cases:
            with self.subTest(size=size, pattern=pattern):
                rows = structured_rows([
                    raw("Shower Wall Tile", True, "100 SF"),
                    raw("PATTERN: " + pattern),
                    raw(f"AREA A SELECTION: {description}: {size}"),
                ])
                self.assertEqual(rows[0]["formula"], f"=ROUND(100*(1+{percent}/100),0)")
                self.assertEqual(rows[0]["measured_qty"], 100)
                self.assertNotRegex(rows[0]["formula"], r"[A-Z]+\d+")
                self.assertIn(f"Review - {percent}%", rows[0]["comments"])

    def test_floor_without_a_parseable_size_uses_configured_floor_default(self):
        rows = structured_rows([
            raw("Floor Tile", True, "32 SF"),
            raw("AREA A SELECTION: FLORENTINE CARRERA"),
        ])
        self.assertEqual(rows[0]["formula"], "=ROUND(32*(1+12/100),0)")

    def test_multiple_products_do_not_duplicate_one_application_measurement(self):
        rows = structured_rows([
            raw("Floor Tile", True, "100 SF"),
            raw("AREA A SELECTION: FIRST: 24x24", qty="100 SF"),
            raw("AREA B SELECTION: SECOND: 24x24", qty="100 SF"),
        ])
        self.assertEqual([row["quantity"] for row in rows], ["", ""])
        self.assertTrue(all(row["comments"].startswith("Review - quantity left blank")
                            for row in rows))

    def test_template_deep_override_changes_rules_without_python_edits(self):
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        template["rules_file"] = str(RULES)
        template["classica_rules"] = {
            "applications": {
                "aliases": {"wet wall": "shower_wall"},
                "presentation": {
                    "shower_wall": {"display": "Wet Wall", "related": "Wet Wall", "priority": 8}
                },
            },
            "quantity": {"waste_rules": [{"name": "editable_default", "percent": 9}]},
            "accessories": {"drain_riser": {"quantity": 2}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.json"
            path.write_text(json.dumps(template), encoding="utf-8")
            loaded = load_template(path)
        configured = rules_for(loaded)
        rows = structured_rows([
            raw("Wet Wall", True, "10 SF"),
            raw("AREA A SELECTION: SAMPLE: 3x12"),
            raw("SHOWER DRAIN: Square", qty="1 EA"),
        ], configured)
        tile = next(row for row in rows if row["application"] == "shower_wall")
        riser = next(row for row in rows if row["type"] == "Drain riser plug")
        self.assertEqual(tile["formula"], "=ROUND(10*(1+9/100),0)")
        self.assertEqual(riser["quantity"], 2)
        self.assertEqual(configured["applications"]["presentation"]["shower_wall"]["display"],
                         "Wet Wall")

    def test_invalid_rule_reports_exact_field(self):
        rules = deepcopy(rules_for())
        rules["quantity"]["waste_rules"][0]["percent"] = -1
        with self.assertRaisesRegex(ValueError, r"quantity\.waste_rules\[0\]\.percent"):
            validate_classica_rules(rules, "test rules")


if __name__ == "__main__":
    unittest.main()
