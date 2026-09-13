import unittest
from pathlib import Path

from scripts.classica_changes import apply_changes, read_changes
from scripts.extract_classica_room import extract, table_rows


def record(text, heading=False, room='GREAT'):
    return {'room': room, 'type_description': text, 'qty': '1 EA',
            'layout': {'is_heading': heading}}


class ChangeTests(unittest.TestCase):
    def test_scoped_add_and_delete_keep_raw_audit(self):
        records = [record('Surround / Thin Brick', True), record('COLOR: Iron Works'),
                   record('Surround / Tile (full wall)', True),
                   record('AREA A SELECTION: Tile (DalTile) Group 1: FAMED: 12x24, Iconic')]
        instructions = [{'order': 1, 'text': 'Fireplace Surround - ADD - Surround - Thin Brick'},
                        {'order': 1, 'text': 'Fireplace Surround - DELETE - Surround: Full Wall Tile'}]
        report = apply_changes(records, instructions)
        self.assertEqual([r['status'] for r in report], ['applied', 'applied'])
        self.assertEqual(len(records), 4)
        self.assertIn('excluded_by_change', records[3])
        self.assertFalse(any('FAMED' in r[2] for r in table_rows(records)))
        self.assertTrue(any('Thin Brick' in r[2] for r in table_rows(records)))

    def test_ambiguous_and_mismatched_changes_do_not_mutate(self):
        for instructions in [
            [{'order': 1, 'text': 'Fireplace Surround - DELETE - Surround: Full Wall Tile'}],
            [{'order': 1, 'text': 'Fireplace Surround - ADD - Surround: Full Wall Tile - Blue mosaic'}],
            [{'order': 1, 'text': 'Fireplace Surround - REPLACE - something unclear'}],
        ]:
            records = [record('Surround / Tile (full wall)', True),
                       record('Surround / Tile (full wall)', True, 'GREATBASE')]
            report = apply_changes(records, instructions)
            self.assertEqual(report[0]['status'], 'review')
            self.assertFalse(any('excluded_by_change' in r for r in records))

    def test_exact_replace_preserves_original(self):
        records = [record('Floor Tile', True, 'BTHF_BR2'),
                   record('AREA A SELECTION: Old Product', room='BTHF_BR2')]
        report = apply_changes(records, [{'order': 2,
            'text': 'Bedroom # 2 Full Bath - REPLACE - "Old Product" WITH "New Product"'}])
        self.assertEqual(report[0]['status'], 'applied')
        self.assertEqual(records[1]['original_description'], 'AREA A SELECTION: Old Product')
        self.assertEqual(records[1]['type_description'], 'AREA A SELECTION: New Product')

    def test_later_change_order_supplies_explicit_wall_areas(self):
        text = '''Change Orders Approved
Included at Start Approved
Change Order #5
\u2022 Tile - Bed #5 Bath Shower - Upgrade tile as follows:
- Main Back Wall: Group 4: Conrad Brick 2x8, Siren. PATTERN: Stacked Horizontal
- Side Walls: Group 4: Conrad Brick 2x8, Sage. PATTERN: Stacked Horizontal
- Grout Color for All Walls: Snow White
- Schluter Trim Color for All Walls: TSBG
NOTE: Price includes credit.
'''
        records = [record('Shower Wall Tile', True, 'BTHF_BR5'),
                   record('*See Change Order for Tile Selection', True, 'BTHF_BR5'),
                   record('PATTERN: Stacked Horizontal', room='BTHF_BR5')]
        report = apply_changes(records, read_changes(text))
        rendered = table_rows(records)
        self.assertEqual(report[0]['status'], 'applied')
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in rendered],
            [('Main Back wall', '2x8', 'Conrad Brick, Siren'),
             ('Side walls', '2x8', 'Conrad Brick, Sage'),
             ('Schluter', '', 'TSBG'), ('Grout', '', 'Snow White')],
        )

    def test_reads_only_current_approved_changes_in_order(self):
        text = '''Change Orders Approved
Change Order #2
\u2022 Fireplace Surround - DELETE - Surround: Full Wall Tile 1/10/2026
continuation
1/14/2026 Lot Example 2
Change Order #1
\ufffd Fireplace Surround - ADD - Surround - Thin Brick
Included at Start Approved
Change Order #0
\u2022 Historical change
'''
        changes = read_changes(text)
        self.assertEqual([c['order'] for c in changes], [1, 2])
        self.assertTrue(changes[1]['text'].endswith('continuation'))
        self.assertNotIn('1/10/2026', changes[1]['text'])

    def test_24_stephens_fireplace_revision(self):
        path = Path(__file__).resolve().parents[1] / 'orginals/Vendor Orders-PDF/VendorOrder_24StephensFarm.pdf'
        if not path.exists():
            self.skipTest('Local reference PDF unavailable')
        result = extract(path, 'GREAT')
        self.assertEqual([c['status'] for c in result['change_report']], ['applied', 'applied'])
        rendered = table_rows(result['rows'])
        self.assertTrue(any('Thin Brick' in r[2] for r in rendered))
        self.assertFalse(any('FAMED' in r[2] for r in rendered))


if __name__ == '__main__':
    unittest.main()
