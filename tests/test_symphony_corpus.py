import io
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
import zipfile

from symphony.corpus import parse_mscx, balanced_probabilities, _safe_member_index, git_blob_sha, ingest


def score(body):
    return ('<museScore><Score><Part><Staff id="1"/><trackName>Violin</trackName>'
            '<Instrument><Articulation><velocity>100</velocity></Articulation></Instrument></Part>'
            '<Staff id="1">' + body + '</Staff></Score></museScore>').encode()


def chord(pitch, duration="quarter", extra="", note_extra=""):
    return f'<Chord><durationType>{duration}</durationType>{extra}<Note><pitch>{pitch}</pitch>{note_extra}</Note></Chord>'


class ScoreCorpusTests(unittest.TestCase):
    def test_ties_dots_and_long_rest_do_not_invent_melodic_attacks(self):
        xml = score('<Measure><voice>' + chord(60) + chord(64, 'eighth', '<dots>1</dots>')
                    + chord(67, note_extra='<Spanner type="Tie"><prev><location/></prev></Spanner>')
                    + '<Rest><durationType>whole</durationType></Rest>' + chord(72)
                    + '</voice></Measure>')
        p = parse_mscx(xml)
        self.assertEqual(p['notehead_count'], 4)
        self.assertEqual(p['pitched_attack_count'], 3)
        self.assertEqual(p['interval_counts'], {'4': 1})
        self.assertEqual(p['duration_counts'], {'1': 2, '3/4': 1})
        self.assertEqual(p['articulation_counts'], {})

    def test_staff_voice_boundaries_preserve_separate_melodies(self):
        xml = score('<Measure><voice>' + chord(60) + chord(62) + '</voice><voice>'
                    + chord(48) + chord(47) + '</voice></Measure><Measure><voice>'
                    + chord(65) + '</voice><voice>' + chord(45) + '</voice></Measure>')
        p = parse_mscx(xml)
        self.assertEqual(p['interval_counts'], {'2': 1, '-1': 1, '3': 1, '-2': 1})
        self.assertEqual(p['interval_transition_counts'], {'2,3': 1, '-1,-2': 1})

    def test_tuplet_and_grace_are_explicit(self):
        xml = score('<Measure><voice><Tuplet id="1"><normalNotes>2</normalNotes><actualNotes>3</actualNotes></Tuplet>'
                    + chord(60, extra='<Tuplet>1</Tuplet>') + chord(61, extra='<acciaccatura/>')
                    + chord(62) + '</voice></Measure>')
        p = parse_mscx(xml)
        self.assertEqual(p['duration_counts'], {'2/3': 1, '1': 1})
        self.assertEqual(p['grace_chord_count'], 1)
        self.assertEqual(p['interval_counts'], {'2': 1})

    def test_excerpt_copies_do_not_override_master_tuplets_or_note_counts(self):
        xml = score('<Measure><voice><Tuplet id="1"><normalNotes>2</normalNotes><actualNotes>3</actualNotes></Tuplet>'
                    + chord(60, extra='<Tuplet>1</Tuplet>') + '</voice></Measure>')
        xml = xml.replace(b'</Score></museScore>',
                          ('<Score><Staff><Measure><voice><Tuplet id="1"><normalNotes>4</normalNotes>'
                           '<actualNotes>5</actualNotes></Tuplet>' + chord(65) + '</voice></Measure></Staff></Score>'
                           '</Score></museScore>').encode())
        p = parse_mscx(xml)
        self.assertEqual(p['notehead_count'], 1)
        self.assertEqual(p['duration_counts'], {'2/3': 1})

    def test_equal_composer_mixture_does_not_follow_prolific_count(self):
        p = balanced_probabilities({'many': {'interval_counts': {'1': 1000}},
                                    'few': {'interval_counts': {'-1': 2}}}, 'interval_counts')
        self.assertEqual(p, {'-1': 0.5, '1': 0.5})

    def test_duplicate_or_unsafe_zip_paths_rejected(self):
        for name in ('../bad.mscx', '/bad.mscx'):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr(name, b'bad')
            with zipfile.ZipFile(data) as z, self.assertRaises(ValueError):
                _safe_member_index(z)

    def test_ingestion_checks_pinned_bytes_and_writes_replayable_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = score('<Measure><voice>' + chord(60) + chord(62) + '</voice></Measure>')
            archive = root / 'fixture.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('fixture-root/', b'')
                z.writestr('fixture-root/scores/Composer/Work/file.mscx', raw)
            sources = {'sources': [{'id': 'fixture', 'archive_url': 'https://example.invalid/not-used',
                                    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}]}
            (root / 'sources.json').write_text(json.dumps(sources))
            row = {'source_id': 'fixture', 'path': 'scores/Composer/Work/file.mscx',
                   'composer': 'Composer', 'git_blob_sha1': git_blob_sha(raw), 'bytes': len(raw)}
            manifest = root / 'files.jsonl'
            manifest.write_text(json.dumps(row) + '\n')
            result = ingest(root / 'sources.json', manifest, root, root / 'out')
            self.assertEqual(result['parsed_score_count'], 1)
            self.assertEqual(result['aggregate']['notehead_count'], 2)
            self.assertEqual(result['balanced']['interval_probabilities'], {'2': 1.0})
            row['git_blob_sha1'] = '0' * 40
            manifest.write_text(json.dumps(row) + '\n')
            with self.assertRaisesRegex(ValueError, 'pinned Git blob'):
                ingest(root / 'sources.json', manifest, root, root / 'out')

    def test_source_git_blob_identity_and_invalid_pitch(self):
        self.assertEqual(git_blob_sha(b'hello\n'), 'ce013625030ba8dba906f756967f9e9ca394464a')
        with self.assertRaisesRegex(ValueError, 'MIDI range'):
            parse_mscx(score('<Measure><voice>' + chord(200) + '</voice></Measure>'))


if __name__ == '__main__':
    unittest.main()
