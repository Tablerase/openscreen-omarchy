# Word-timing harness

Scores transcript word times against exact ground truth: how far each word
boundary is from the audio, and what deleting one word or one phrase in the
transcript editor would leave audible or clip. Method, baseline and plan:
issue #948. How the app times words:
[transcription-and-captions.md § Word-level alignment](../../../technical-documentation/architecture/transcription-and-captions.md).

Node 22+, no dependencies. The corpus is synthesized with Windows speech
synthesis, so generating it needs Windows; scoring runs anywhere.

## Data

Everything generated goes to `data/` next to these scripts (gitignored), or
wherever `OSC_WORD_TIMING_DATA` points:

- `clips/`: `<id>.wav` (clean), `<id>.noisy.wav`, `<id>.ref.json` (reference words)
- `corpus-manifest.json`
- `results/raw/<tag>/`: the helper's raw responses; `results/<name>.{txt,json}`: scores

## Generate the corpus (Windows, once, about 5 min)

```sh
node make-corpus.mjs     # 48 TTS clips + a noisy copy of each + reference times
node validate-ref.mjs    # checks the reference against the audio's energy
```

- Voices: OneCore Hortense, Paul and Julie (French), SAPI Zira (English).
  Scripts are in `corpus-texts.mjs`, synthesis in `tts.ps1`.
- ffmpeg: `electron/native/bin/win32-x64/ffmpeg.exe`, or set `FFMPEG`.

## Run and score

```sh
node run-helper.mjs <tag> <path/to/whisper-stt-server.exe> [--cpu]
node evaluate.mjs <tag> [--snap <post-pass.ts>] [--out <name>]
node summarize.mjs "Before=<baseline>" "After=<name>"
```

- `run-helper.mjs` starts its own helper on a port in 20500-20599 with the
  app's models (`%APPDATA%/openscreen/stt-models/whisper-ggml`: `ggml-small-q8_0.bin`
  and `ggml-silero-v6.2.0.bin`), sends every clip like the app does, and stops
  it. Vulkan takes about 2 min for the 55 min of audio, CPU about 17.
- `evaluate.mjs` parses the responses as `whisperServer.ts` does and runs the
  post-pass: the repo's `electron/stt/snapWordBoundaries.ts` by default, or the
  file given with `--snap`. It reports three stages: `raw`, `post` (no speech
  intervals) and `post+vad` (what the app ships).
- A baseline is the same two commands on an older helper and post-pass:
  build the helper at that revision, and pass
  `git show <rev>:electron/stt/snapWordBoundaries.ts` saved to a file as `--snap`.

## Real speech

```sh
node real-check.mjs <whisper-stt-server.exe> take.wav   # 16 kHz mono s16
```

No ground truth there: it prints how far each word's first-token time lies after
its start, and where each phrase's first word lands against the VAD onset, raw
and after the post-pass.

## Reading the numbers

- Positions come from the reference: *phrase-initial* has a pause of at least
  100 ms before it, *phrase-final* after it, *inner* is everything else.
- A delete is *clean* when at most 20 ms of the deleted word stays audible and
  at most 20 ms of its neighbours is cut.
- Synthetic speech flatters every method. Use the harness to rank approaches,
  and check a winner on real speech.
