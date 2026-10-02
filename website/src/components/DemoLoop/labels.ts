/**
 * What each loop shows, for anyone who cannot see it. The loops carry no words
 * of their own, so the same files serve all eight locales and only these
 * labels are translated.
 *
 * Built at render, like the Showcase copy: translate() answers in the locale
 * being rendered, so this cannot be a module-level constant.
 */

import { translate } from "@docusaurus/Translate";

import type { LoopName } from "../../lib/demo-loop";

const LOOP = "Describes a short silent video loop of the app for screen readers.";

export function loopLabel(name: LoopName): string {
	switch (name) {
		case "classic-zoom":
			return translate({
				id: "demoLoop.classic-zoom",
				description: LOOP,
				message:
					"A task board recorded in OpenScreen. The view zooms in on a checklist item and a Ship button as they are clicked, then pulls back to the whole board.",
			});
		case "3d-camera":
			return translate({
				id: "demoLoop.3d-camera",
				description: LOOP,
				message:
					"The same recording seen through the 3D camera, which tilts the screen and orbits around it while it follows the cursor.",
			});
		case "3d-cursors":
			return translate({
				id: "demoLoop.3d-cursors",
				description: LOOP,
				message:
					"One recorded pointer, redrawn in five cursor styles one after another while the recording keeps playing.",
			});
		case "automatic-subtitles":
			return translate({
				id: "demoLoop.automatic-subtitles",
				description: LOOP,
				message:
					"A narrated recording with captions under it, switching from English to French, Spanish and Korean.",
			});
		case "caption-styles":
			return translate({
				id: "demoLoop.caption-styles",
				description: LOOP,
				message:
					"One caption shown in five styles: a plain caption, a bold yellow one, a handwritten one, a monospaced one, and one highlighted word by word.",
			});
		case "edit-by-transcript":
			return translate({
				id: "demoLoop.edit-by-transcript",
				description: LOOP,
				message:
					"In the editor's transcript, a sentence is selected and deleted, and the matching cut appears on the timeline.",
			});
		case "tighten-pauses":
			return translate({
				id: "demoLoop.tighten-pauses",
				description: LOOP,
				message:
					"Two clicks on the silence markers in the transcript, and both pauses are cut from the timeline.",
			});
		case "background-picker":
			return translate({
				id: "demoLoop.background-picker",
				description: LOOP,
				message:
					"The editor's background picker going through wallpapers, a gradient and a solid color, then turning on the animated Aurora background.",
			});
		case "every-format":
			return translate({
				id: "demoLoop.every-format",
				description: LOOP,
				message:
					"The same recording exported in 16:9, then square, then vertical, with the framing following the cursor.",
			});
		case "sensitive-data-mask":
			return translate({
				id: "demoLoop.sensitive-data-mask",
				description: LOOP,
				message:
					"A sign-in form being filled in. The email and password fields stay blurred while they are typed.",
			});
		case "camera-cutout":
			return translate({
				id: "demoLoop.camera-cutout",
				description: LOOP,
				message:
					"A webcam bubble over a screen recording. Its background is then removed, leaving the speaker in front of the screen.",
			});
		case "every-layout":
			return translate({
				id: "demoLoop.every-layout",
				description: LOOP,
				message:
					"One recording with a webcam, cycling through the layouts: picture in picture, side by side, stacked, full camera, then screen only.",
			});
		case "device-frames":
			return translate({
				id: "demoLoop.device-frames",
				description: LOOP,
				message:
					"The same playing recording framed in turn as a browser window, a phone, a laptop and a desktop monitor.",
			});
		case "animated-backgrounds":
			return translate({
				id: "demoLoop.animated-backgrounds",
				description: LOOP,
				message:
					"A recording on a plain background, then on a blurred photo background that moves slowly behind it.",
			});
		case "beautiful-by-default":
			return translate({
				id: "demoLoop.beautiful-by-default",
				description: LOOP,
				message:
					"A raw screen capture, then the same take as OpenScreen opens it, already zoomed, framed and with a restyled cursor, then in several looks.",
			});
		case "simpler-editor":
			return translate({
				id: "demoLoop.simpler-editor",
				description: LOOP,
				message:
					"The OpenScreen editor. One click on a background thumbnail restyles the whole video, then the side panel switches to the transcript.",
			});
		case "edit-like-a-doc":
			return translate({
				id: "demoLoop.edit-like-a-doc",
				description: LOOP,
				message:
					"Text selected in the transcript is deleted like text in a document, and the video is cut to match.",
			});
		case "ask-the-agent":
			return translate({
				id: "demoLoop.ask-the-agent",
				description: LOOP,
				message:
					"A request typed into the editor's chat panel, and the edits the agent makes appearing on the timeline.",
			});
	}
}
