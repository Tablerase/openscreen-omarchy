// Prepare transparent cursor PNGs from the Blender renders in design/cursors.
// Run with `node scripts/generate-original-cursor-themes.mjs`.
// Each source PNG contains the arrow on the left and the hand on the right.

import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_DIR = path.join(ROOT, "design", "cursors");
const PUBLIC_DIR = path.join(ROOT, "public", "cursors");
const SIZE = 128;
const INNER_SIZE = 112;

// Each Blender scene writes arrow-tip and fingertip positions in source-image pixels.
const themeIds = ["studio-ink", "prism-glow", "pop-coral", "pixel-candy", "star-sprout"];
const themeNames = ["Studio Ink", "Prism Glow", "Pop Coral", "Pixel Candy", "Star Sprout"];

const browser = await chromium.launch();
try {
	const page = await browser.newPage();
	await page.goto("about:blank");
	const previewSprites = [];
	for (const id of themeIds) {
		const theme = {
			id,
			hotspots: JSON.parse(await readFile(path.join(SOURCE_DIR, id, "hotspots.json"), "utf8")),
		};
		const output = path.join(PUBLIC_DIR, theme.id);
		await mkdir(output, { recursive: true });
		const source = await readFile(path.join(SOURCE_DIR, theme.id, "source.png"));
		const sprites = {};
		for (const type of ["arrow", "pointer"]) {
			for (const filename of [`${type}-sdf.png`, `${type}-sdf.json`, `${type}-color.png`]) {
				await copyFile(path.join(SOURCE_DIR, theme.id, filename), path.join(output, filename));
			}
			const result = await page.evaluate(
				async ({ png, type, size, innerSize, hotspot }) => {
					const image = new Image();
					image.src = `data:image/png;base64,${png}`;
					await image.decode();
					const halfWidth = image.width / 2;
					const sourceX = type === "arrow" ? 0 : halfWidth;
					const sourceCanvas = document.createElement("canvas");
					sourceCanvas.width = halfWidth;
					sourceCanvas.height = image.height;
					const sourceContext = sourceCanvas.getContext("2d", { willReadFrequently: true });
					sourceContext.drawImage(image, -sourceX, 0);
					const pixels = sourceContext.getImageData(0, 0, halfWidth, image.height);
					let minX = halfWidth;
					let minY = image.height;
					let maxX = 0;
					let maxY = 0;
					for (let y = 0; y < image.height; y++) {
						for (let x = 0; x < halfWidth; x++) {
							const alphaIndex = (y * halfWidth + x) * 4 + 3;
							if (pixels.data[alphaIndex] < 28) {
								pixels.data[alphaIndex] = 0;
								continue;
							}
							minX = Math.min(minX, x);
							minY = Math.min(minY, y);
							maxX = Math.max(maxX, x);
							maxY = Math.max(maxY, y);
						}
					}
					if (minX > maxX || minY > maxY) throw new Error("Empty cursor artwork");
					sourceContext.putImageData(pixels, 0, 0);
					const width = maxX - minX + 1;
					const height = maxY - minY + 1;
					const scale = innerSize / Math.max(width, height);
					const targetWidth = width * scale;
					const targetHeight = height * scale;
					const targetX = (size - targetWidth) / 2;
					const targetY = (size - targetHeight) / 2;
					const canvas = document.createElement("canvas");
					canvas.width = canvas.height = size;
					const context = canvas.getContext("2d");
					context.imageSmoothingQuality = "high";
					context.drawImage(
						sourceCanvas,
						minX,
						minY,
						width,
						height,
						targetX,
						targetY,
						targetWidth,
						targetHeight,
					);
					return {
						png: canvas.toDataURL("image/png").split(",")[1],
						hotspotX: (targetX + (hotspot[0] - sourceX - minX) * scale) / size,
						hotspotY: (targetY + (hotspot[1] - minY) * scale) / size,
					};
				},
				{
					png: source.toString("base64"),
					type,
					size: SIZE,
					innerSize: INNER_SIZE,
					hotspot: theme.hotspots[type],
				},
			);
			const filename = `${type}.png`;
			await writeFile(path.join(output, filename), Buffer.from(result.png, "base64"));
			sprites[type] = result.png;
			console.log(
				`${theme.id}/${filename}: hotspot ${result.hotspotX.toFixed(4)}, ${result.hotspotY.toFixed(4)}`,
			);
		}
		previewSprites.push({ id, name: themeNames[themeIds.indexOf(id)], sprites });
	}
	const sheets = await page.evaluate(async (themes) => {
		const imageFromBase64 = async (base64) => {
			const image = new Image();
			image.src = `data:image/png;base64,${base64}`;
			await image.decode();
			return image;
		};
		const contact = document.createElement("canvas");
		contact.width = 328;
		contact.height = 820;
		const contactContext = contact.getContext("2d");
		contactContext.fillStyle = "#ebeff6";
		contactContext.fillRect(0, 0, contact.width, contact.height);
		contactContext.font = "12px Arial, sans-serif";
		contactContext.fillStyle = "#2a2f39";
		for (let row = 0; row < themes.length; row++) {
			const theme = themes[row];
			const y = row * 164;
			contactContext.fillText(theme.name, 10, y + 18);
			for (const [column, type] of ["arrow", "pointer"].entries()) {
				const image = await imageFromBase64(theme.sprites[type]);
				contactContext.drawImage(image, 18 + column * 164, y + 28, 128, 128);
			}
		}

		const dark = document.createElement("canvas");
		dark.width = 112;
		dark.height = 280;
		const darkContext = dark.getContext("2d");
		darkContext.fillStyle = "#141822";
		darkContext.fillRect(0, 0, dark.width, dark.height);
		for (let row = 0; row < themes.length; row++) {
			for (const [column, type] of ["arrow", "pointer"].entries()) {
				const image = await imageFromBase64(themes[row].sprites[type]);
				darkContext.drawImage(image, 12 + column * 56, row * 56 + 12, 32, 32);
			}
		}
		return { contact: contact.toDataURL("image/png"), dark: dark.toDataURL("image/png") };
	}, previewSprites);
	await writeFile(
		path.join(SOURCE_DIR, "contact-sheet.png"),
		Buffer.from(sheets.contact.split(",")[1], "base64"),
	);
	await writeFile(
		path.join(SOURCE_DIR, "dark-32px.png"),
		Buffer.from(sheets.dark.split(",")[1], "base64"),
	);
} finally {
	await browser.close();
}
