# OpenScore ingestion for expressive composition

This pipeline downloads and parses the complete pinned OpenScore Lieder and OpenScore String Quartets archives. The source editions are released under CC0; their license texts are retained here. Credit OpenScore Lieder, OpenScore String Quartets and their volunteer transcription teams, with links to https://github.com/OpenScore/Lieder and https://github.com/OpenScore/StringQuartets.

The pinned corpus contains 1,352 song editions and 122 quartet editions: 1,474 score files by 136 distinct composer directory identities. These are not 136 recorded performers. The raw score XML totals 1,791,630,171 bytes; the downloaded repository archives total 804,951,803 bytes and include other source material. Archives live under the ignored `results/symphony_corpus/` cache. The repository retains the source manifest, exact source score identities, derived per-score counts and composer-balanced priors rather than duplicating the entire corpus.

Run from the repository root:

```bash
python -m symphony.corpus
python -m unittest discover -s tests -p test_symphony_corpus.py
```

`sources.json` fixes repository revisions, archive URLs, archive SHA256 values and edition licenses. `files.jsonl` lists every source score's path, composer directory, Git blob SHA1 and exact size. Ingestion verifies the archives, requires an exact match to the planned score set, checks every raw score against its Git identity, computes SHA256 and rejects altered bytes. Identical raw bytes are counted once; this is byte deduplication, not a semantic catalogue of distinct musical works or editions. The parser does not read lyric files or extract embedded images.

The parser visits only master-score staves. Embedded excerpt/part copies are excluded from note counts and from tuplet/tie lookups. A top-note chord reduction supplies a melodic stream per staff and voice. Tied continuations do not add new attacks; grace chords are counted separately; rests lasting at least four quarter-note beats reset melodic continuity. Notated durations include dots and tuplet ratios. Repeat signs are not unfolded. The parser counts score heads, attacks, durations, melodic intervals, interval transitions, explicit dynamics and articulations. These do not establish human performance timing, vibrato, orchestral timbre or listener preference.

`data/symphony/corpus_profile.json` contains raw aggregate histograms, each composer's histograms, the composer list and balanced probabilities. For each histogram the balanced distribution is the equal-weight mixture of normalized composer distributions with observations. A prolific composer therefore does not dominate merely by contributing more files. Signed interval keys are semitone integer strings; transition keys are `previous,next`; duration keys are rational strings in quarter-note beats. `data/symphony/corpus_index.jsonl` preserves source SHA256, raw size, score-level counts and parser failures.

Composition uses these as statistical priors and constraints. It does not claim to train a neural model, recreate a named performer's interpretation or prove aesthetic superiority. Written dynamics and articulations inform designed expression; recorded-performance datasets would be needed to estimate performed rubato, articulation timing or vibrato empirically.
