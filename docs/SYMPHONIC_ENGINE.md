# Symphonic composition and performance

The primary musical output is an original scored performance with structure, recurring thematic material, orchestration, dynamics and playable audio. The software uses an authored composition grammar, empirical musical priors and a sampled orchestral renderer. It does not claim to train a neural orchestra, reproduce a particular pianist, or prove aesthetic quality numerically. The prepared recordings let listeners assess the result directly.

## Actual data ingestion

The complete pinned OpenScore Lieder and String Quartets sources contain **1,474 score editions by 136 composer directory identities**, totaling **1,791,630,171 bytes of score XML**. All files were parsed and checked against their planned Git identity and SHA256: **2,602,628 notated noteheads**, **2,491,550 pitched attacks** and **2,048,608 melodic transitions**, with zero parse failures or unresolved durations. The source editions are CC0; source licenses and credits are retained in `symphony/corpus_sources/`. Source repetitions are not unfolded, embedded part copies are excluded, and top-note melodic streams are measured separately by staff and voice.

The separate ATEPP/ASAP pipeline parsed **12,741 performed MIDI files**, with **35,530,748 completed note records**, **49 named pianists** and **27 canonical performance-source composers**. The composer populations overlap; these counts must not be added into an inflated combined total. ATEPP provides automatic transcriptions of piano recordings, while ASAP provides performed MIDI and aligned beat annotations. All files parsed. Quality flags, exact-byte duplicate exclusion and a composition holdout leave **8,064 fitting performances / 21,654,108 notes**, including all 49 pianists; **2,393 performance records** are held out. Held-out predictive or listening superiority has not been established by merely setting these records aside.

The score priors average normalized histograms equally across composers. Dynamic priors average by work within named pianist, then equally across pianists; timing priors balance ASAP works and composers. This avoids treating the most prolific source as the universal musician. MIDI velocity is a performance-control value, not physical force. Piano timing/velocity priors inform bounded authored orchestral mappings; piano data do not determine bowing, breathing, conductor interpretation or instrumental timbre.

Inspect `data/symphony/corpus_profile.json`, `corpus_index.jsonl`, `corpus_receipt.json`, `performance_profile.json`, `performance_index.csv.gz`, `performance_sources.json` and `PERFORMANCE_DATA.md`. ATEPP's CC BY 4.0 and ASAP's CC BY-NC-SA 4.0 provenance is documented separately; the original performed data are not republished here. Raw archives remain in the ignored cache, with pinned URLs, byte counts and SHA256 checks for automatic refetch.

## Composition and expression

The composer builds a three-movement tonal narrative. Two original themes recur through different keys, rhythm, register, instrumentation and transformations. Cadences, breaths, rests, harmonic plans and larger dynamic shapes are authored. A melodic beam search scores new candidates using composer-balanced interval and interval-transition priors alongside thematic contour, chord-tone priorities, register, leap recovery and repetition limits. Corpus duration priors score the available rhythmic figures. The source melodies are not retrieved and assembled into the output.

Inner strings follow close chord-tone voice leading. Winds answer melodic phrases; the scherzo separates bass beats from short inner-string replies; harp colors selected harmonic changes; brass and timpani enter at structural peaks. Source priors are creative constraints, not evidence that the result matches every composer's style. `all`, `romantic`, `luminous` and `classical` palettes select explicitly documented composer mixtures.

Performance uses one continuous phrase clock for the whole ensemble. Local rubato, cadence preparation, part-correlated arrivals, articulation, dynamic arcs, delayed vibrato and individual note envelopes preserve musical coherence. Written velocities remain within a bounded adjustment, avoiding silent sample layers. Measured piano-performance statistics and their mapping formulas are recorded in each performed score. Bow, breath and phrase trajectories remain authored. This is more specific than adding independent random offsets to quantized notes.

The actual recovered `dyletsky-gen2-43` solver supplies the static `hex_nat` offset field, retained at `data/symphony/dyletsky_profile.json`. Each note keeps its spelling: C-sharp is not replaced by D-flat. The composer currently uses key-aware spelling choices within the recovered 17-label vocabulary. Per-note render channels preserve different cents within a chord. This is a separate musical program; it does not change the frozen E4 experiment.

## Audible rendering and playback

GeneralUser GS 2.0.3 supplies real instrument samples through FluidSynth. The renderer layers bowed parts, applies per-note cents and vibrato, shapes sustained-note expression, places sections in stereo and adds room response. Pizzicato uses the recorded pizzicato patch. It writes an actual PCM master and an MP3 copy; it opens no audio or actuator device. Asset source/license/hash and native dependency recipes are in `assets/symphony/`. A single global normalization preserves the performance's relative dynamic contour. Tested native playback uses 64 logical channels with explicit channel exhaustion checks.

The player embeds MP3, MIDI and performed event timing in one HTML file. Play/Pause, seek, movement chapters, volume, speed, loop, downloads and responsive layout are real controls over the recorded performance. The animated stage and score are synchronized to that audio. Offline listening needs no Python or sample-bank installation. The MIDI is a portable equal-tempered export with timing, dynamics and shared-section expression; audio retains the individual microtonal trajectories.

The current physical object has four strings and a common exciter. The software orchestra supplies the multi-instrument sound heard in these recordings. Assembly and a validated sensor-to-conductor mapping are still needed before clay gestures or hydrophone signals control the music physically; the player does not display fictitious live sensor controls. No automatic tuner is the product objective of this musical workstream.

## Reproduce and compose

Prepared audio and players are under `music/`. To rebuild them, use Python 3.11 or newer, NumPy, ffmpeg and FluidSynth with the pinned SoundFont. The tested NumPy version is 2.3.5. On compatible Linux x86_64, the asset bootstrap can prepare the isolated native dependencies automatically. Windows listeners can simply open the prepared HTML or MP3; native regeneration needs a working FluidSynth library for that operating system.

```bash
python -m pip install -r symphony/requirements.txt
python assets/symphony/fetch_soundfont.py --native-linux
python -m symphony build --output-dir results/my_symphony
python -m symphony build --title "My chamber symphony" --palette luminous --seed 81 --bars-scale 2 --output-dir results/my_second_symphony
python -m symphony compose --output results/editable_written_score.json --seed 82
python -m unittest discover -s tests -p 'test_symphony*.py'
```

To rerun the high-volume analyses instead of using the committed profiles:

```bash
python -m symphony.corpus
python -m symphony.performance_data --download --workers 4
```

The longer prepared piece was built with `--bars-scale 2 --palette romantic --seed 20261025`; the shorter piece uses the complete palette and seed 20261024. Each build saves written/performed JSON, MIDI, MP3, a self-contained player and a receipt linking source-profile digests, composition choices and render parameters. Longer forms remain subject to the renderer's declared duration and channel limits.
