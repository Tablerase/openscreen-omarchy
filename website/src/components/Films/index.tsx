/**
 * Films of the app, under the editor: a centred head, a wide stage, and the
 * notes that say what the film just showed.
 *
 * A stage with several loops plays them in turn. Each plays once, its tab
 * filling as it goes, then hands over to the next; a click on a tab jumps
 * there. Everything about loading and playback (nothing fetched before the
 * stage is near, 720p or 1080p from the real width, pause off screen, no
 * autoplay under reduced motion, a pause button) is DemoLoop's.
 */

import { translate } from "@docusaurus/Translate";
import Heading from "@theme/Heading";
import { useCallback, useRef, useState } from "react";

import DemoLoop from "../DemoLoop";
import { type Block, getBlocks, getPair } from "./content";
import styles from "./styles.module.css";

function Stage({ block }: { block: Block }) {
	const [index, setIndex] = useState(0);
	const bars = useRef<(HTMLSpanElement | null)[]>([]);
	const many = block.tabs.length > 1;
	const current = block.tabs[index];

	// Straight to the DOM: a state update per frame would re-render the block.
	const onProgress = useCallback(
		(p: number) => bars.current[index]?.style.setProperty("--p", String(p)),
		[index],
	);
	const go = (i: number) => {
		bars.current.forEach((el) => el?.style.setProperty("--p", "0"));
		setIndex(i);
	};

	return (
		<div className={styles.stage}>
			<span className={styles.glow} />
			{many && (
				<div className={styles.tabs} role="tablist" aria-label={block.title}>
					{block.tabs.map((tab, i) => (
						<button
							key={tab.loop}
							type="button"
							role="tab"
							id={`${block.id}-tab-${i}`}
							aria-selected={i === index}
							aria-controls={`${block.id}-panel`}
							className={styles.tab}
							onClick={() => go(i)}
						>
							{tab.label}
							<span
								ref={(el) => {
									bars.current[i] = el;
								}}
								className={styles.tabProgress}
								aria-hidden="true"
							/>
						</button>
					))}
				</div>
			)}
			<div
				className={styles.frame}
				id={`${block.id}-panel`}
				role={many ? "tabpanel" : undefined}
				aria-labelledby={many ? `${block.id}-tab-${index}` : undefined}
			>
				<DemoLoop
					key={current.loop}
					name={current.loop}
					loop={!many}
					onProgress={many ? onProgress : undefined}
					onEnded={many ? () => go((index + 1) % block.tabs.length) : undefined}
				/>
			</div>
		</div>
	);
}

export default function Films() {
	const pair = getPair();
	return (
		<section
			className={styles.section}
			aria-label={translate({
				id: "films.label",
				description: "Read by screen readers only: names the section of feature videos",
				message: "More of the app, in motion",
			})}
		>
			<div className={styles.inner}>
				{getBlocks().map((block) => (
					<article key={block.id} id={block.id} className={styles.block}>
						<header className={styles.head}>
							<p className={styles.kicker}>{block.kicker}</p>
							<Heading as="h2" className={styles.title}>
								{block.title}
							</Heading>
							<p className={styles.lead}>{block.lead}</p>
						</header>
						<Stage block={block} />
						<ul className={styles.notes}>
							{block.notes.map((note, i) => (
								<li key={i} className={styles.note}>
									{note}
								</li>
							))}
						</ul>
					</article>
				))}

				<article id={pair.id} className={styles.block}>
					<header className={styles.head}>
						<p className={styles.kicker}>{pair.kicker}</p>
						<Heading as="h2" className={styles.title}>
							{pair.title}
						</Heading>
						<p className={styles.lead}>{pair.lead}</p>
					</header>
					<div className={styles.pair}>
						{pair.items.map((item) => (
							<div key={item.loop} className={styles.pairItem}>
								<div className={styles.frame}>
									<DemoLoop name={item.loop} />
								</div>
								<p className={styles.pairCaption}>{item.caption}</p>
							</div>
						))}
					</div>
				</article>
			</div>
		</section>
	);
}
