// Sanity check on real speech, which has no ground truth: the VAD onset is the
// only boundary we can trust there.
// Usage: node real-check.mjs <whisper-stt-server.exe> <take.wav> [--cpu] [--snap <post-pass.ts>]
//   (16 kHz mono s16 WAV, e.g. ffmpeg -i take.webm -ar 16000 -ac 1 take.wav)
// Prints how far each word's first-token time (`anchor`) lies after its start
// (the one-token lag the helper corrects), and, per VAD stretch, where its first
// word starts relative to the onset: as the helper reports it, and after the
// post-pass. Writes the raw response to <data>/results/real-<take>.json.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { REPO, RESULTS, startHelper, transcribe } from "./lib.mjs";

const [exe, wav, ...rest] = process.argv.slice(2);
if (!exe || !wav)
	throw new Error(
		"usage: node real-check.mjs <whisper-stt-server.exe> <take.wav> [--cpu] [--snap <post-pass.ts>]",
	);
const snapAt = rest.indexOf("--snap");
const snapPath = path.resolve(
	snapAt >= 0 ? rest[snapAt + 1] : path.join(REPO, "electron/stt/snapWordBoundaries.ts"),
);
const { anchorWordsOnSpeech } = await import(pathToFileURL(snapPath).href);

const { base, stop } = await startHelper(exe, { cpu: rest.includes("--cpu") });
let json;
try {
	({ json } = await transcribe(base, wav));
} finally {
	stop();
}
mkdirSync(RESULTS, { recursive: true });
writeFileSync(path.join(RESULTS, `real-${path.basename(wav, ".wav")}.json`), JSON.stringify(json));

const isP = (w) => /^[\p{P}\p{S}]+$/u.test(w.word);
const raw = json.segments
	.flatMap((s) => s.words)
	.map((w) => ({
		word: w.word.trim(),
		startSec: w.start,
		endSec: Math.max(w.start + 0.02, w.end),
		anchorSec: w.anchor ?? w.start,
	}))
	.filter((w) => w.word);
const speech = json.speech.map((s) => ({ startSec: s.start, endSec: s.end }));
const post = anchorWordsOnSpeech(raw, speech);
const lag = raw
	.filter((w) => !isP(w))
	.map((w) => w.anchorSec - w.startSec)
	.sort((a, b) => a - b);
const q = (p) => (lag[Math.floor(lag.length * p)] * 1000).toFixed(0);
console.log(
	`${json.detected_language}, ${raw.length} words; first-token time minus start: median ${q(0.5)} ms, p10 ${q(0.1)}, p90 ${q(0.9)}`,
);
const ms = (x) => `${x >= 0 ? "+" : ""}${(x * 1000).toFixed(0)} ms`;
let k = 0;
for (const [i, s] of speech.entries()) {
	const tail = Math.min(s.endSec + 0.1, speech[i + 1]?.startSec ?? Number.POSITIVE_INFINITY);
	while (k < raw.length && isP(raw[k])) k++;
	if (k >= raw.length || raw[k].anchorSec >= tail) continue;
	console.log(
		`stretch ${s.startSec.toFixed(2)}-${s.endSec.toFixed(2)}: "${raw[k].word}" starts ${ms(raw[k].startSec - s.startSec)} from the onset raw, ${ms(post[k].startSec - s.startSec)} after the post-pass`,
	);
	while (k < raw.length && raw[k].anchorSec < tail) k++;
}
