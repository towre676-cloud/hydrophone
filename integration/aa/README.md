# A&A transport integration

Copy `orchestral-soundtrack.js` beside the game's `adaptive-soundtrack.js` and `soundtrack.js`. Copy `music/aa-adaptive/audio` and `manifest.json` to `dist/game/music/aa-adaptive/`. Copy `listen.html` and `audition.mp3` there for a playable audition page.

In `engine2/main.js`, import `OrchestralSoundtrack as Soundtrack`, `attachOrchestralLibrary`, `orchestratedProgram` and `gameplayIntensity` from the new transport. Load the manifest during boot, extend the existing music library with:

```js
attachOrchestralLibrary(musicLibrary, manifest,
  new URL('../music/aa-adaptive/', import.meta.url));
```

Pass `orchestratedProgram(musicProgram, manifest)` as the director's `programFor`. Existing pause, volume, unlock, selected-performance and dialogue-ducking controls keep their existing transport calls. Call `audio.setIntensity(gameplayIntensity({battle,scene:world.scene,state:world.state}))` in soundtrack synchronization and the half-second audio meter update.

Route `rpgCue` event IDs to `orchestra:victory_sting`, `orchestra:combat_exit`, `orchestra:revelation`, `orchestra:chapter_ending`, `orchestra:rest` and `orchestra:boss_arrival` as appropriate, falling back to the previous library if the new manifest is unavailable. Call the boss-arrival event once when the boss encounter begins. Scene routing preserves explicit silence and selected performances. The manifest's story and rest rules are integration contracts; only observed call sites establish which events a particular game emits.

The actual A&A source patch is included as `game-integration.patch`, against inspected source commit `50cf0efe5d9a49808512672a4c9cd2594cce60a2`. Apply after copying the transport and delivery files. The dedicated checkout prevents modifying ongoing scenery work in another working directory.

Tests use a deterministic Web Audio clock to verify scheduling and cancellation. Run `node --test integration/aa/orchestral-soundtrack.test.mjs`. The existing A&A music director, music program and transport suites were also run (46 tests). The listening room's “Check every delivery file” control exercises actual browser decoding and SHA256 verification; its meter exposes real audio output and transport state.
