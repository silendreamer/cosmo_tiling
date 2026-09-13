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

    def test_complete_room_table_wins_over_older_wall_prose_without_placeholder(self):
        records = [record('Shower Wall Tile', True, 'BTH_BR3S'),
                   record('AREA A SELECTION: MESMERIST: 3x12, Whimsy, MM34', room='BTH_BR3S')]
        instruction = {'order': 5, 'text':
            'Tile - Bed #3 Shared Bath Shower - Change material to: '
            '- MAIN BACK WALL: Group 4: Mythology 4x12, Aura, MY95 '
            '- SIDE WALLS: Group 4: Mythology 4x12, Olympus, MY95 '
            '- Grout Color for All Walls: Ash - Schluter Trim Color for All Walls: Gray'}
        report = apply_changes(records, [instruction])
        self.assertEqual([(item[0], item[1], item[2]) for item in table_rows(records)],
                         [('Shower Wall Tile', '3x12', 'MESMERIST, Whimsy, MM34')])
        self.assertEqual(report[0]['status'], 'ignored')

    def test_checkerboard_and_later_clarifications_resolve_floor_placeholder(self):
        records = [record('Floor Tile', True, 'BTHF_PRIM'),
                   record('*See Change Order for Tile Selection', True, 'BTHF_PRIM')]
        instructions = [
            {'order': 5, 'text': 'Tile Floor - Primary Bath - ADD - CHECKERBOARD - Group 3: Perpetuo: 24x24, White, PT20 AND Group 3: Perpetuo: 24x24, Beige, PT22 - Grout: TBD Schluter: TBD.'},
            {'order': 12, 'text': 'Tile - Primary Bath Floor Tile - CLARIFICATION - Grout Color: Warm Gray - Tile Selection on CO #5'},
            {'order': 12, 'text': 'Tile - Primary Bath Floor Tile - CLARIFICATION - Schluter Color: TSBG - Tile Selection on CO #5'},
        ]
        report = apply_changes(records, instructions)
        rows = table_rows(records)
        self.assertEqual([item[2] for item in rows],
                         ['Perpetuo, White, PT20', 'Perpetuo, Beige, PT22', 'TSBG', 'Warm Gray'])
        self.assertTrue(all(item['status'] == 'applied' for item in report))
        self.assertTrue(all(item['application'] == 'floor' for item in report))

    def test_latest_unique_niche_add_resolves_placeholder(self):
        records = [record('Wall Niche / Schluter / Model (12x12)', True, 'BTHF_BR5'),
                   record('See Change Order for new niche selection', True, 'BTHF_BR5')]
        instructions = [
            {'order': 6, 'text': 'Tile - Bed #5 Full Bath Shower Niche - ADD - Group 4: Stagecraft 3x12 Navy - Installed in niche'},
            {'order': 12, 'text': 'Tile Options - Bed 5 Bath Shower Niche - ADD - Grp 7 Uptown Glass 1x1 Ebony UP22 - Same grout'},
        ]
        report = apply_changes(records, instructions)
        rows = table_rows(records)
        self.assertTrue(any(item[1] == '1x1' and 'Uptown Glass' in item[2] for item in rows))
        self.assertEqual(report[1]['status'], 'applied')
        self.assertEqual(report[1]['room'], 'BTHF_BR5')

    def test_backplash_extension_without_new_product_removes_only_placeholder(self):
        records = [record('Backsplash / Tile', True, 'KITCHEN/inc Pantry'),
                   record('See Change Order for backsplash around windows', True, 'KITCHEN/inc Pantry'),
                   record('AREA A SELECTION: Tile (DalTile) Group 4: SAMPLE: 3x12, White', False,
                          'KITCHEN/inc Pantry')]
        instructions = [{'order': 4,
                         'text': 'Tile Backsplash - Kitchen - Carry Tile Up & Around Windows'}]
        report = apply_changes(records, instructions)
        rows = table_rows(records)
        self.assertEqual(rows[0][1:3], ['3x12', 'SAMPLE, White'])
        self.assertEqual(report[0]['status'], 'applied')

    def test_drain_placeholder_requires_unique_room_and_application(self):
        records = [record('Shower Floor Tile', True, 'BTHF_BR5'),
                   record('See Change Order for Linear Drain', True, 'BTHF_BR5')]
        instructions = [{'order': 3,
                         'text': 'Shower Drain - Bedroom #5 Full Bath - ADD - Linear Drain'}]
        report = apply_changes(records, instructions)
        rows = table_rows(records)
        self.assertEqual(rows[:2], [['Shower Drain', '', 'Linear Drain', '', ''],
                                   ['Drain riser plug', '', 'Drain riser plug', 1, 'EA']])
        self.assertEqual(report[0]['application'], 'drain')

    def test_missing_or_ambiguous_approved_change_keeps_placeholder_for_review(self):
        for instructions in [[], [
            {'order': 1, 'text': 'Tile - Bed #5 Bath - Wall Tile - Main Back Wall - Group 1: A 2x8, One'},
            {'order': 1, 'text': 'Tile - Bed #5 Bath - Wall Tile - Main Back Wall - Group 1: B 2x8, Two'},
        ]]:
            records = [record('Shower Wall Tile', True, 'BTHF_BR5'),
                       record('See Change Order for Tile Selection', True, 'BTHF_BR5')]
            report = apply_changes(records, instructions)
            self.assertTrue(any('See Change Order' in item[2] for item in table_rows(records)))
            self.assertTrue(any(item['status'] == 'review' and item.get('room') == 'BTHF_BR5'
                                for item in report))

    def test_without_approved_heading_change_order_text_is_ignored(self):
        self.assertEqual(read_changes('Change Order #5\n\u2022 Tile - Bed #5 Bath - ADD - Group 1: A'), [])

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
