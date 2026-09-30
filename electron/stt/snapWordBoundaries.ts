// Pulls whisper.cpp's DTW word boundaries back onto the audio they describe.
//
// whisper.cpp reports one time per token and derives word spans from it, so a
// word's `start` is the point where the decoder *emitted* the token, not where
// the speaker started saying it. Measured on real recordings, that lands
// consistently 80–150 ms late, and because consecutive words share a boundary
// (`word[i].end === word[i+1].start`) the whole transcript is dragged right by
// roughly a syllable.
//
// That is invisible in captions but not in the transcript editor: deleting
// words there turns the selection into a trim of exactly
// `[firstWord.startSec, lastWord.endSec]`, so a late boundary leaves the attack
// of the first removed word audible and bites into the following kept word.
//
// The correction is to look at the audio instead of guessing an offset: each
// boundary moves back to the quietest 10 ms frame within the preceding
// `LOOKBACK_SEC`. It is self-limiting — on a decaying tail (a word that ends a
// phrase, where whisper is already right) the quietest frame IS the reported
// one, so the boundary doesn't move at all.
//
// The edges of a phrase are the exception. Its first word, DTW reports 0.1–0.6 s
// late (measured against Silero VAD on a real French recording), far past what
// the lookback can reach; its last word ends where whisper's segment ends, which
// can stop short of the speech. When the helper sent its speech intervals, both
// are pulled onto the edges of the stretch of speech they belong to.

import type { SttVadSegment, SttWordSegment } from "./transcriptionContract";

/** Matches `writeSamplesAsWav` — the samples handed to whisper are mono 16 kHz. */
const SAMPLE_RATE = 16_000;

/** RMS envelope resolution; finer than any boundary error worth correcting. */
const FRAME_SEC = 0.01;

/**
 * How far back a boundary may travel — the calibration knob for this
 * correction. Sized to the measured DTW lag (~80–150 ms). Widen it and
 * boundaries inside continuous speech start snapping onto the *previous*
 * syllable's trough; narrow it and the lag survives.
 */
const LOOKBACK_SEC = 0.15;

/** Keep degenerate words (whisper sometimes reports end <= start) non-empty. */
const MIN_WORD_SEC = 0.02;

/**
 * How far a phrase's first word may start after its speech, or its last word
 * end before it, and still be pulled onto that edge — the calibration knob of
 * the anchoring step, sized above the measured 0.1–0.6 s. Past it, the word is
 * more likely a neighbour of one whisper dropped, and stretching it over that
 * audio would be a guess.
 */
const MAX_ANCHOR_SEC = 1;

/** French puts a space before `!`, `?`, `:` and `;`, so whisper emits them as words. */
const isPunctuation = (word: string) => /^[\p{P}\p{S}]+$/u.test(word);

/** Per-frame RMS of the mono signal — the cheapest usable "is this speech" proxy. */
function rmsEnvelope(samples: Float32Array): Float32Array {
	const frameLength = Math.round(SAMPLE_RATE * FRAME_SEC);
	const frameCount = Math.floor(samples.length / frameLength);
	const envelope = new Float32Array(frameCount);
	for (let f = 0; f < frameCount; f++) {
		const start = f * frameLength;
		let sum = 0;
		for (let i = start; i < start + frameLength; i++) {
			const v = samples[i] ?? 0;
			sum += v * v;
		}
		envelope[f] = Math.sqrt(sum / frameLength);
	}
	return envelope;
}

/**
 * Pull the first and last word of every speech stretch onto the stretch's
 * edges. The onset already carries the VAD's 30 ms pad, so a cut there lands
 * just before the attack. What sits past an edge moves with it: the previous
 * word's shared boundary, and any punctuation DTW dropped inside the speech,
 * which collapses to a point on the edge.
 */
function anchorOnSpeech(words: SttWordSegment[], speech: SttVadSegment[]): SttWordSegment[] {
	const out = words.map((w) => ({ ...w }));
	let k = 0;
	for (let i = 0; i < speech.length; i++) {
		const { startSec: onset, endSec: offset } = speech[i];
		const previousEnd = i > 0 ? speech[i - 1].endSec : Number.NEGATIVE_INFINITY;
		// The phrase's first word: the first real word reported after the previous stretch ended.
		while (k < out.length && (out[k].startSec < previousEnd || isPunctuation(out[k].word))) k++;
		if (k === out.length) break;
		const late = out[k].startSec - onset;
		if (late > 0 && late <= MAX_ANCHOR_SEC && out[k].startSec < offset) {
			out[k].startSec = onset;
			for (let j = k - 1; j >= 0 && out[j].endSec > onset; j--) {
				out[j].endSec = onset;
				out[j].startSec = Math.min(out[j].startSec, onset);
			}
		}
		// Its last word: the last real word reported before the speech stops.
		let m = -1;
		for (let j = k; j < out.length && out[j].startSec < offset; j++) {
			if (!isPunctuation(out[j].word)) m = j;
		}
		const early = m < 0 ? 0 : offset - out[m].endSec;
		if (early > 0 && early <= MAX_ANCHOR_SEC) {
			out[m].endSec = offset;
			for (let j = m + 1; j < out.length && out[j].startSec < offset; j++) {
				out[j].startSec = offset;
				out[j].endSec = Math.max(out[j].endSec, offset);
			}
		}
	}
	return out;
}

/**
 * Move every word boundary back to the quietest frame in the `LOOKBACK_SEC`
 * preceding it. Boundaries shared by two words snap identically (same input
 * time), so the transcript stays gap-free where whisper made it gap-free.
 * With `speech` (the helper's VAD intervals), phrase edges are then anchored
 * on the speech. Returns the words unchanged when there is no audio to
 * measure against.
 */
export function snapWordBoundariesToAudio(
	words: SttWordSegment[],
	samples: Float32Array,
	speech?: SttVadSegment[],
): SttWordSegment[] {
	const envelope = rmsEnvelope(samples);
	if (envelope.length === 0) return words;

	const lookbackFrames = Math.round(LOOKBACK_SEC / FRAME_SEC);
	const snap = (timeSec: number): number => {
		const hi = Math.round(timeSec / FRAME_SEC);
		// A boundary outside the audio we can measure (whisper occasionally reports
		// times past the end of the samples) has nothing to snap to — clamping it
		// into range would drag it to the end of the buffer instead.
		if (hi <= 0 || hi >= envelope.length) return timeSec;
		const lo = Math.max(0, hi - lookbackFrames);
		let bestFrame = hi;
		let bestRms = envelope[hi];
		// Strict `<` while walking backwards keeps the frame CLOSEST to the
		// reported boundary when a whole stretch is equally quiet, so digital
		// silence can't drag a boundary the full window.
		for (let f = hi - 1; f >= lo; f--) {
			if (envelope[f] < bestRms) {
				bestRms = envelope[f];
				bestFrame = f;
			}
		}
		return bestFrame * FRAME_SEC;
	};

	const snapped = words.map((w) => {
		const startSec = snap(w.startSec);
		return {
			...w,
			startSec,
			endSec: Math.max(snap(w.endSec), startSec + MIN_WORD_SEC),
		};
	});
	return speech ? anchorOnSpeech(snapped, speech) : snapped;
}
