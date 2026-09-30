import { describe, expect, it } from "vitest";
import { snapWordBoundariesToAudio } from "./snapWordBoundaries";
import type { SttWordSegment } from "./transcriptionContract";

const SAMPLE_RATE = 16_000;

/** Mono 16 kHz buffer that is loud everywhere except the given silent spans. */
function audioWithSilences(durationSec: number, silences: Array<[number, number]>): Float32Array {
	const samples = new Float32Array(Math.round(durationSec * SAMPLE_RATE));
	for (let i = 0; i < samples.length; i++) {
		const t = i / SAMPLE_RATE;
		const silent = silences.some(([from, to]) => t >= from && t < to);
		// Alternating ±0.5 gives a flat, non-zero RMS without needing a real tone.
		samples[i] = silent ? 0 : i % 2 === 0 ? 0.5 : -0.5;
	}
	return samples;
}

const word = (w: Partial<SttWordSegment> = {}): SttWordSegment => ({
	word: "w",
	startSec: 0,
	endSec: 0.1,
	...w,
});

describe("snapWordBoundariesToAudio", () => {
	it("pulls a late boundary back into the silence that precedes it", () => {
		// Speech stops at 1.0 and resumes at 1.2; whisper reports the next word
		// starting at 1.3 — 100 ms after the audio actually resumed.
		const samples = audioWithSilences(3, [[1.0, 1.2]]);
		const [snapped] = snapWordBoundariesToAudio([word({ startSec: 1.3, endSec: 1.8 })], samples);
		expect(snapped.startSec).toBeGreaterThanOrEqual(1.0);
		expect(snapped.startSec).toBeLessThan(1.2);
	});

	it("leaves a boundary alone when nothing quieter precedes it", () => {
		// A word ending a phrase: whisper is already right, the frames before the
		// boundary are all speech, so the quietest frame in the window is the
		// boundary itself and it must not drift.
		const samples = audioWithSilences(3, [[1.5, 2.0]]);
		const [snapped] = snapWordBoundariesToAudio([word({ startSec: 1.0, endSec: 1.5 })], samples);
		expect(snapped.endSec).toBeCloseTo(1.5, 2);
	});

	it("never moves a boundary more than the lookback window", () => {
		const samples = audioWithSilences(3, [[0.0, 1.0]]);
		const [snapped] = snapWordBoundariesToAudio([word({ startSec: 2.0, endSec: 2.5 })], samples);
		expect(snapped.startSec).toBeGreaterThanOrEqual(2.0 - 0.15);
	});

	it("keeps a boundary shared by two words shared", () => {
		const samples = audioWithSilences(3, [[1.0, 1.2]]);
		const [first, second] = snapWordBoundariesToAudio(
			[word({ startSec: 0.5, endSec: 1.3 }), word({ startSec: 1.3, endSec: 1.8 })],
			samples,
		);
		expect(first.endSec).toBeCloseTo(second.startSec, 6);
	});

	it("leaves boundaries that fall outside the decoded audio alone", () => {
		// Clamping these into range would collapse every boundary onto the end of
		// the buffer instead of leaving the unmeasurable ones untouched.
		const samples = audioWithSilences(0.1, []);
		const words = [word({ startSec: 5.51, endSec: 6.85 })];
		expect(snapWordBoundariesToAudio(words, samples)).toEqual(words);
	});

	it("keeps degenerate words non-empty and passes words through without audio", () => {
		const samples = audioWithSilences(3, [[1.0, 1.2]]);
		const [degenerate] = snapWordBoundariesToAudio([word({ startSec: 1.3, endSec: 1.3 })], samples);
		expect(degenerate.endSec).toBeGreaterThan(degenerate.startSec);

		const untouched = [word({ startSec: 1.3, endSec: 1.8 })];
		expect(snapWordBoundariesToAudio(untouched, new Float32Array(0))).toEqual(untouched);
	});
});

describe("snapWordBoundariesToAudio with speech intervals", () => {
	// Loud and flat everywhere, so the RMS snap moves nothing and only the
	// anchoring on `speech` is under test.
	const flat = audioWithSilences(6, []);
	const ms = (sec: number) => Math.round(sec * 1000) / 1000;
	const times = (words: SttWordSegment[]) =>
		words.map((w) => [w.word, ms(w.startSec), ms(w.endSec)]);

	it("puts each phrase's first word on its onset and its closing punctuation on its end", () => {
		// The shape of a real French take: whisper put "Salut" 0.58 s and "Bah"
		// 0.25 s after the speech started, ran "Salut" on through the pause, and
		// dropped the "!" closing the first phrase just after the second began.
		const words = [
			word({ word: "Salut", startSec: 2.15, endSec: 3.37 }),
			word({ word: "!", startSec: 3.37, endSec: 3.39 }),
			word({ word: "Bah", startSec: 3.61, endSec: 4.01 }),
			word({ word: "voilà", startSec: 4.01, endSec: 4.35 }),
		];
		const speech = [
			{ startSec: 1.57, endSec: 2.56 },
			{ startSec: 3.36, endSec: 4.35 },
		];
		expect(times(snapWordBoundariesToAudio(words, flat, speech))).toEqual([
			["Salut", 1.57, 2.56],
			["!", 2.56, 2.56],
			["Bah", 3.36, 4.01],
			["voilà", 4.01, 4.35],
		]);
	});

	it("ends each phrase's last word where its speech stops, stretched or cut back", () => {
		// The end of the same take: "tic," ran on into the pause, whisper closed
		// the last segment at 2.79 while "tac" ran to 3.04, and dropped the "!" on
		// the word itself.
		const words = [
			word({ word: "tic,", startSec: 1.95, endSec: 2.59 }),
			word({ word: "tac", startSec: 2.59, endSec: 2.79 }),
			word({ word: "!", startSec: 2.62, endSec: 2.79 }),
		];
		const speech = [
			{ startSec: 1.95, endSec: 2.37 },
			{ startSec: 2.59, endSec: 3.04 },
		];
		expect(times(snapWordBoundariesToAudio(words, flat, speech))).toEqual([
			["tic,", 1.95, 2.37],
			["tac", 2.59, 3.04],
			["!", 3.04, 3.04],
		]);
	});

	it("leaves a phrase alone when its words are on time, or too far off to be its edges", () => {
		const onTime = [word({ startSec: 0.95, endSec: 3 })];
		expect(times(snapWordBoundariesToAudio(onTime, flat, [{ startSec: 1, endSec: 3 }]))).toEqual(
			times(onTime),
		);
		// 1.2 s after the onset and 1.1 s before the offset: more likely a neighbour
		// of words whisper dropped than the phrase's own edges.
		const tooFar = [word({ startSec: 2.2, endSec: 2.5 })];
		expect(times(snapWordBoundariesToAudio(tooFar, flat, [{ startSec: 1, endSec: 3.6 }]))).toEqual(
			times(tooFar),
		);
	});

	it("never mistakes a phrase's second word for its first", () => {
		// "y" opens the second phrase but was reported just before its onset;
		// "z" must not be dragged back over it.
		const words = [
			word({ word: "x", startSec: 0.5, endSec: 1.95 }),
			word({ word: "y", startSec: 1.95, endSec: 2.4 }),
			word({ word: "z", startSec: 2.4, endSec: 3 }),
		];
		const speech = [
			{ startSec: 0.5, endSec: 1 },
			{ startSec: 2, endSec: 3 },
		];
		expect(times(snapWordBoundariesToAudio(words, flat, speech))).toEqual([
			["x", 0.5, 1],
			["y", 1.95, 2.4],
			["z", 2.4, 3],
		]);
	});

	it("does not take a word in the previous phrase's tail for the next one's first", () => {
		// The helper keeps 0.1 s past each offset. "b" was reported in the first
		// phrase's tail, and "c" still has to reach the second onset.
		const words = [
			word({ word: "a", startSec: 1, endSec: 2.05 }),
			word({ word: "b", startSec: 2.05, endSec: 3.4 }),
			word({ word: "c", startSec: 3.4, endSec: 4 }),
		];
		const speech = [
			{ startSec: 1, endSec: 2 },
			{ startSec: 3, endSec: 4 },
		];
		expect(times(snapWordBoundariesToAudio(words, flat, speech))).toEqual([
			["a", 1, 2.05],
			["b", 2.05, 2.07],
			["c", 3, 4],
		]);
	});
});
