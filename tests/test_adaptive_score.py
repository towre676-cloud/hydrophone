import hashlib
import json
import unittest
from symphony.adaptive.build import score, CUES, BARS, BAR
from symphony.render import validate_score

class AdaptiveScoreTests(unittest.TestCase):
    def test_all_arrangements_are_distinct_valid_and_synchronized(self):
        hashes=set()
        for kind in CUES:
            for v in range(3):
                s=score(kind,v); events=validate_score(s)
                self.assertEqual(set(e['stem'] for e in events),{'bed','theme','motion'})
                self.assertTrue(all(0<=e['start_s']<BARS*BAR for e in events))
                self.assertTrue(all(e['start_s']+e['duration_s']<=BARS*BAR for e in events))
                hashes.add(hashlib.sha256(json.dumps(s['events'],sort_keys=True).encode()).hexdigest())
        self.assertEqual(len(hashes),24)
    def test_endings_resolve_the_final_melodic_bar_to_tonic(self):
        for kind in CUES:
            s=score(kind,0,4,ending=True)
            lead=[e for e in s['events'] if e['stem']=='theme' and e['start_s']>=3*BAR and e['instrument']==CUES[kind][1]]
            self.assertTrue(all(e['midi_pitch']%12==2 for e in lead))
