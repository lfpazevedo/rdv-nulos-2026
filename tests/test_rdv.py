"""Decoder check on one public section (BA, municipality 30007, zone 0205, section 0177, runoff 2026).

Run: python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rdv import bu_president, rdv_votes  # noqa: E402

FIX = Path(__file__).parent / 'fixtures'


class TestSection(unittest.TestCase):
    def setUp(self):
        self.rdv = rdv_votes((FIX / 'o03221ba3000702050177-rdv.dat').read_bytes())
        self.bu = bu_president((FIX / 'o03221ba3000702050177-bu.dat').read_bytes())

    def test_rdv_president(self):
        pres = {(t, d): v for (office, t, d), v in self.rdv.items() if office == 1}
        self.assertEqual(pres, {(2, '13'): 108, (2, '22'): 199, (3, ''): 3,
                                (4, '00'): 2, (4, '11'): 1, (4, '24'): 1})

    def test_bu_president(self):
        self.assertEqual(self.bu['candidates'], {'13': 108, '22': 199})
        self.assertEqual((self.bu['blank'], self.bu['null'], self.bu['turnout']), (3, 4, 314))


if __name__ == '__main__':
    unittest.main()
