/**
 * Where the demo loops live and which file a reader gets.
 *
 * The loops are served from Cloudflare R2, not from website/static/. Everything
 * under static/ is committed to git for good (scripts/check-media-budget.mjs
 * says why), and eighteen 1080p60 clips in two codecs and two sizes are about
 * 50 MB per cut. The bucket holds them outside the repository; the folder name
 * is the cut, so a re-encode goes to a new folder and the old files can keep
 * their `immutable` cache header.
 */

export const LOOP_BASE = "https://media.getopenscreen.com/loops/2026-10";

export const LOOP_NAMES = [
	"classic-zoom",
	"3d-camera",
	"3d-cursors",
	"automatic-subtitles",
	"caption-styles",
	"edit-by-transcript",
	"tighten-pauses",
	"background-picker",
	"every-format",
	"sensitive-data-mask",
	"camera-cutout",
	"every-layout",
	"device-frames",
	"animated-backgrounds",
	"beautiful-by-default",
	"simpler-editor",
	"edit-like-a-doc",
	"ask-the-agent",
] as const;

export type LoopName = (typeof LOOP_NAMES)[number];

export type LoopHeight = 720 | 1080;

/**
 * The smaller file whenever it is sharp enough. Every loop is 16:9, so the
 * height a box needs is its width × 9/16 in device pixels. The ratio is capped
 * at 2: a 3× phone shows a column a few hundred CSS pixels wide, where 720 rows
 * are already more than it can resolve.
 */
export function pickHeight(cssWidth: number, devicePixelRatio: number): LoopHeight {
	const dpr = Math.min(Math.max(devicePixelRatio || 1, 1), 2);
	const rows = (cssWidth * dpr * 9) / 16;
	return rows > 760 ? 1080 : 720;
}

/**
 * The codec strings are the encoder's real profile and level (ffprobe on the
 * files), not the bare "hvc1": an engine that can decode HEVC Main only up to a
 * lower level should say no here and take the H.264 file, rather than say yes
 * and stall. HEVC is listed first: about 40% smaller at the same VMAF.
 */
export function loopSources(name: LoopName, height: LoopHeight) {
	return [
		{
			src: `${LOOP_BASE}/${name}-${height}-hevc.mp4`,
			type: `video/mp4; codecs="hvc1.1.6.L${height === 1080 ? 123 : 120}.B0"`,
		},
		{
			src: `${LOOP_BASE}/${name}-${height}-h264.mp4`,
			type: `video/mp4; codecs="avc1.64002a"`,
		},
	];
}

export function loopPoster(name: LoopName): string {
	return `${LOOP_BASE}/${name}-poster.webp`;
}
