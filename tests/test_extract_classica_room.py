"""Regression checks for the standalone column-inspection script."""
import unittest
from pathlib import Path

from scripts.extract_classica_room import APPLICATION_ALIASES, LABEL_ALIASES, extract, size_match, table_rows


def row(text, heading=False, qty="1 EA"):
    return {"type_description": text, "qty": qty, "selection_changed": "",
            "layout": {"is_heading": heading}}


class ApplicationDetectionTests(unittest.TestCase):
    def test_multiple_drains_preserved(self):
        rows = table_rows([
            row("Shower Drain : Square"), row("Shower Drain Finish : Gold [A]"),
            row("shower drain: Round"), row("shower drain finish: Black [B]"),
        ])
        self.assertEqual([r[0] for r in rows],
                         ["Shower Drain", "Drain riser plug", "Shower Drain", "Drain riser plug"])
        self.assertEqual(rows[0][1:3], ["[A]", "Square- Gold"])
        self.assertEqual(rows[2][1:3], ["[B]", "Round- Black"])

    def test_label_variations_and_conditional_trim(self):
        rows = table_rows([
            row("BACKSPLASH / Tile", True),
            row("Area A Selection : tile (DalTile) Group 1: SAMPLE: 3x12, White"),
            row("Schluter: (Napa & Tiburon Plan Only): AMGB (brass)"),
            row("Grout Colour : Ash (642)"),
        ])
        self.assertEqual(rows[0][1:3], ["3x12", "SAMPLE, White"])
        self.assertEqual(rows[1][2], "AMGB (brass)")
        self.assertEqual(rows[-1][2], "Ash (642) sanded")

    def test_dimensions_preserve_fractions_and_reject_ambiguity(self):
        for text in ['1 1/2 x 3', '1/2 X 3', '1\u00bd \u00d7 3', '12" x12"', '8.5x10']:
            with self.subTest(text=text):
                self.assertEqual(size_match(text).group(), text)
        for text in ['1/0 x 3', '12x24x3', '12x24 or 10x20', 'ABC12x24', '1.2.3x4']:
            with self.subTest(text=text):
                self.assertIsNone(size_match(text))
        rows = table_rows([row("Floor Tile", True),
                          row("AREA A SELECTION: SAMPLE: 12x24 sheet, 1x3 mosaic")])
        self.assertEqual(rows[0][1], "12x24")
        self.assertIn('1x3 mosaic', rows[0][2])

    def test_variants_share_order_caulk_and_niche_association(self):
        rows = table_rows([
            row("Bathroom Type / Tub and Shower", True),
            row("Floor Tile/Upgrade flooring", True),
            row("AREA A SELECTION: FLOOR: 12x24, White"),
            row("GROUT COLOR: White"),
            row("Shower Walls / Tile to ceiling", True),
            row("AREA A SELECTION: WALL: 3x12, Blue"),
            row("SCHLUTER: AMGB"), row("GROUT COLOR: Blue"),
            row('wall niche / Schluter / 12" x12"', True),
            row("Tile Option (inside of niche): same AS Shower Wall Tile"),
        ])
        self.assertEqual([r[0] for r in rows], ["Shower Walls / Tile to ceiling", "Schluter",
                         "Schluter niche", "Grout", "Caulk", "Floor Tile/Upgrade flooring", "Grout", "Caulk"])

    def test_ambiguous_niche_stays_standalone(self):
        rows = table_rows([
            row("Shower Wall Tile / Main", True), row("AREA A SELECTION: FIRST: 12x24"),
            row("Shower Wall Tile / Side", True), row("AREA A SELECTION: SECOND: 12x24"),
            row('Wall Niche / Schluter / 12" x12"', True),
            row("TILE OPTION (inside of niche): Same as Shower Wall Tile"),
        ])
        self.assertEqual([r[0] for r in rows],
                         ["Shower Wall Tile / Main", "Shower Wall Tile / Side", "Schluter niche"])

    def test_alias_overrides(self):
        rows = table_rows([
            row("Bathroom flooring", True), row("Product choice: SAMPLE: 12x24, White"),
        ], {**APPLICATION_ALIASES, "bathroom flooring": "floor"},
           {**LABEL_ALIASES, "product choice": "selection"})
        self.assertEqual(rows[0][:3], ["Bathroom flooring", "12x24", "SAMPLE, White"])

    def test_new_instruction_and_unknown_heading(self):
        rows = table_rows([
            row("Floor Tile", True), row("Lay parallel to the doorway", True, qty=""),
            row("AREA A SELECTION: FIRST: 12x24"),
            row("New mystery application", True, qty=""),
            row("AREA A SELECTION: SECOND: 12x24"),
        ])
        self.assertEqual(rows[0][0], "Floor Tile")
        self.assertEqual([r[0] for r in rows[1:]], ["Unclassified (review)"] * 3)

    def test_caulk_conditions(self):
        for bath, application, expected in [
            ("Shower/ Tub Combination", "Shower Wall Tile", True),
            ("Shower/ Tub Combination", "Floor Tile", True),
            ("Shower/ Tub Combination", "Shower Floor Tile", False),
            ("Full Shower", "Shower Wall Tile", False),
            ("", "Floor Tile", False),
            ("", "Backsplash / Tile", True),
            ("", "Scullery Backsplash", True),
            ("", "Scullery Floor", False),
        ]:
            with self.subTest(bath=bath, application=application):
                rows = table_rows([
                    *([row(f"Bathroom Type / {bath}", True)] if bath else []),
                    row(application, True),
                    row("AREA A SELECTION: Tile (DalTile) Group 1: SAMPLE: 12x24, White"),
                    row("GROUT COLOR:: Ash (642)"),
                ])
                caulk = [r for r in rows if r[0] == "Caulk"]
                self.assertEqual(bool(caulk), expected)
                if expected:
                    self.assertEqual(rows[-2][0], "Grout")
                    self.assertEqual(caulk, [["Caulk", "", "Ash (642) sanded", "", "PCS"]])

    def test_caulk_requires_color(self):
        rows = table_rows([row("Backsplash / Tile", True),
                          row("AREA A SELECTION: Tile (DalTile) Group 1: SAMPLE: 12x24, White"),
                          row("GROUT: Premium grout"), row("GROUT COLOR:: ")])
        self.assertFalse(any(r[0] == "Caulk" for r in rows))

    def test_drain_riser_rule(self):
        rows = table_rows([row("SHOWER DRAIN: Square")])
        self.assertEqual(rows[0][0], "Shower Drain")
        self.assertEqual(rows[1], ["Drain riser plug", "", "Drain riser plug", 1, "EA"])
        self.assertEqual(table_rows([]), [])

    def test_known_application_variant_and_multiple_selections(self):
        rows = table_rows([
            row("Floor Tile", True),
            row("AREA A SELECTION: Tile (DalTile) Group 1: FIRST: 12x24, White", qty="10 SF"),
            row("Surround / Tile (full wall)", True),
            row("AREA A SELECTION: Tile (DalTile) Group 1: SECOND: 2x8, Blue", qty="20 SF"),
            row("AREA B SELECTION: Tile (DalTile) Group 1: THIRD: 2x8, Green", qty="20 SF"),
            row("GROUT COLOR:: Gray"),
        ])
        self.assertEqual([r[0] for r in rows],
                         ["Floor Tile", "Surround / Tile (full wall)", "Surround / Tile (full wall)", "Grout"])
        self.assertEqual(rows[-1][2], "Gray")

    def test_unknown_application_selections_remain_unclassified(self):
        rows = table_rows([
            row("Floor Tile", True),
            row("AREA A SELECTION: Tile (DalTile) Group 1: FIRST: 12x24, White"),
            row("Fireplace Surround Finish", True),
            row("AREA A SELECTION: Tile (DalTile) Group 1: SECOND: 2x8, Blue"),
        ])
        self.assertEqual([r[0] for r in rows],
                         ["Floor Tile", "Unclassified (review)", "Unclassified (review)"])

    def test_instruction_does_not_steal_selection(self):
        rows = table_rows([
            row("Floor Tile", True),
            row("PERPENDICULAR TO W/D LOCATION", True, qty=""),
            row("AREA A SELECTION: Tile (DalTile) Group 1: FIRST: 12x24, White"),
        ])
        self.assertEqual(rows[0][0], "Floor Tile")
        self.assertEqual(rows[1][:3],
                         ["Unclassified (review)", "", "PERPENDICULAR TO W/D LOCATION"])

    def test_ambiguous_section_does_not_leak_accessories(self):
        rows = table_rows([
            row("Floor Tile", True),
            row("AREA A SELECTION: Tile (DalTile) Group 1: FIRST: 12x24, White"),
            row("Unfamiliar fitting", True),
            row("GROUT COLOR:: Red"),
        ])
        self.assertEqual([r[0] for r in rows],
                         ["Floor Tile", "Unclassified (review)", "Unclassified (review)"])

    def test_missing_layout_preserves_selection_for_review(self):
        raw = row("AREA A SELECTION: Unknown product")
        del raw["layout"]
        self.assertEqual(table_rows([raw])[0][0], "Unclassified (review)")

    def test_reference_pdf(self):
        path = Path(__file__).resolve().parents[1] / "pdf/classica/VendorOrder_PalosVerdeEstates7.pdf"
        if not path.exists():
            self.skipTest("Local reference PDF unavailable")
        result = extract(path, "BTHF_BR2")
        self.assertEqual(len(result["rows"]), 25)
        self.assertEqual(len(result["room_codes"]), 9)
        rows = table_rows(result["rows"])
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[1], ["Drain riser plug", "", "Drain riser plug", 1, "EA"])
        self.assertEqual(rows[2][:3], ["Shower Wall Tile", "12x24", "CALLIGO, Tusk, Fluted, CA41"])
        self.assertEqual(rows[4][:3], ["Schluter niche", '12" x12"', "Schluter niche"])
        self.assertTrue(rows[3][2].startswith("AMGB"))
        self.assertEqual(rows[10][2], "TSC (cream)")

    def test_niche_placement_is_independent_of_interior(self):
        rows = table_rows([
            row("Shower Wall Tile", True), row("AREA A SELECTION: WALL: 12x24, White"),
            row("SCHLUTER: MBW"), row("GROUT COLOR: White"),
            row("Shower Floor Tile", True), row("FLOORING SELECTION: FLOOR: 1x3, Blue"),
            row('Wall Niche / Double niche 28\ufffd x 12\ufffd', True),
            row('on wall behind bench', True, qty=''),
            row("TILE OPTION (inside of niche): Same as Shower Floor Tile"),
        ])
        kinds = [r[0] for r in rows]
        self.assertEqual(kinds[:5], ['Shower Wall Tile', 'Schluter', 'Schluter niche', 'Accent', 'Grout'])
        self.assertEqual(rows[2][1], '28" x 12"')
        self.assertEqual(rows[3][1:3], ['1x3', 'FLOOR, Blue'])

    def test_explicit_corner_shelf(self):
        rows = table_rows([
            row('Corner Shelf / Large (Included)', True),
            row('CONTEMPORARY CORNER SHELF (Dal Tile) [BA6801P]'),
            row('CONTEMPORARY SHELF: Group 1: Gray (CN13)'),
            row('Shower Wall Tile', True), row('AREA A SELECTION: WALL: 12x24'),
            row('SCHLUTER: TSC'), row('GROUT COLOR: Gray'),
        ])
        self.assertEqual([r[0] for r in rows], ['Shower Wall Tile', 'Schluter', 'Corner Shelf', 'Grout'])
        self.assertEqual(rows[2][1], '[BA6801P]')
        self.assertIn('Gray (CN13)', rows[2][2])

    def test_sealer_requires_explicit_stone(self):
        for material, expected in [('Stone', True), ('Tile', False)]:
            rows = table_rows([row('Floor Tile', True),
                              row(f'AREA A SELECTION: {material} (DalTile) Group 1: MARBLE LOOK: 12x24'),
                              row('GROUT COLOR: Gray')])
            self.assertEqual(any(r[0] == 'Sealer' for r in rows), expected)

    def test_long_pdf_note_does_not_become_quantity(self):
        path = Path(__file__).resolve().parents[1] / 'orginals/Vendor Orders-PDF/VendorOrder_13StephensFarm.pdf'
        if not path.exists():
            self.skipTest('Local reference PDF unavailable')
        raw = extract(path, 'BTHF_BR4')['rows']
        note = next(r for r in raw if '2 rows of pink' in r['type_description'])
        self.assertEqual(note['qty'], '')
        self.assertIn('arctic gloss', note['type_description'])
        rendered = table_rows(raw)
        self.assertTrue(any(r[0] == 'Shower Wall Tile' and 'AE04' in r[2] for r in rendered))


if __name__ == "__main__":
    unittest.main()
