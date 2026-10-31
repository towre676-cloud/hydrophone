# The listening room

**Clay and Water — Chamber Symphony No. 1** is an original three-movement work lasting 6 minutes and 0.47 seconds, with 1,960 performed note events. [Listen to MP3](clay_and_water/performance.mp3), or download and open [the self-contained player](clay_and_water/player.html). Its themes move through a reflective opening, a lighter scherzo and a returning major-key finale. The romantic prior palette balances the selected source composers; the complete ingested score corpus contains 136 composers.

**The Water Remembers** is an original three-movement miniature lasting 3 minutes and 4.03 seconds, with 961 performed note events. [Listen to MP3](the_water_remembers/performance.mp3), or download and open [the self-contained player](the_water_remembers/player.html). It uses the complete composer-balanced prior palette.

The HTML players contain the actual audio and a MIDI download. No server, online account or installation is required to listen after downloading. Use Play/Pause, movement chapters, the timeline, volume, playback speed and loop. GitHub displays HTML as source; use its raw-file download, save the `.html` file and open it in a browser. Audio files also open in ordinary media players. `run_symphony.bat` in the repository root opens the longer prepared work on Windows.

Each folder retains its written score, performed score, MIDI and build receipt. These are software-rendered original compositions using recorded instrument samples, not a recording of a live orchestra or the physical clay/string/water object. Audio preserves the recovered Dyletsky spelling-dependent cents, per-note envelopes and vibrato. The portable standard MIDI export retains timing, velocities, programs, pan and shared-section expression; its notes are equal-tempered, as stated in the MIDI metadata.

The composition and performance architecture, measured corpus counts, source licenses and reproducible build instructions are in [the engine documentation](../docs/SYMPHONIC_ENGINE.md).

## Ash & Aether adaptive score

[Adaptive Orchestral Book I](aa-adaptive/README.md) adds 24 coordinated loop arrangements across eight gameplay families and six finite event/ending cues. Each arrangement has synchronized bed, theme and motion stems, editable scores, MIDI, lossless FLAC masters and game-ready Vorbis delivery. The [manifest](aa-adaptive/manifest.json), [decoded-audio checks](aa-adaptive/validation.json) and [transition checks](aa-adaptive/transition-validation.json) accompany a reproducible `python -m symphony.adaptive` build. The original recordings above remain unchanged.
