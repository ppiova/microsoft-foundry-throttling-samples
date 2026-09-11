"""Keep the public slide deck free of private presenter assets."""
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit, parse_qs

ASSETS = Path(__file__).parent


class PublicSlidesTests(unittest.TestCase):
    def test_deck_contains_fourteen_sections_and_no_private_controls(self):
        html = (ASSETS / 'slides.html').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'id="slide-(\d+)"', html), [str(i) for i in range(1, 15)])
        for name in ('slides.html', 'slides.js', 'slides.css'):
            content = (ASSETS / name).read_text(encoding='utf-8')
            for marker in ('SPEAKER_NOTES', 'notes-toggle', '/presenter', 'show-notes', 'toggleNotes'):
                self.assertNotIn(marker, content)
        self.assertFalse((ASSETS / 'speaker-notes.json').exists())
        self.assertIn('href="/#experiment"', html)

    def test_microsoft_sources_preserve_mvp_attribution(self):
        html = (ASSETS / 'slides.html').read_text(encoding='utf-8')
        links = re.findall(r'href="(https://learn\.microsoft\.com/[^\"]+)"', html)
        self.assertGreaterEqual(len(links), 5)
        for link in links:
            self.assertEqual(parse_qs(urlsplit(link).query)['WT.mc_id'], ['AI-MVP-5004753'])
