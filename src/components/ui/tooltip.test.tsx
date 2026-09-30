// @vitest-environment jsdom
import "@testing-library/jest-dom";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Tooltip, TooltipProvider } from "./tooltip";

class StubResizeObserver {
	observe() {
		return undefined;
	}
	unobserve() {
		return undefined;
	}
	disconnect() {
		return undefined;
	}
}

beforeEach(() => {
	vi.stubGlobal("ResizeObserver", StubResizeObserver);
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	vi.useRealTimers();
});

function renderTooltip(props: Partial<React.ComponentProps<typeof Tooltip>> = {}) {
	render(
		<TooltipProvider>
			<Tooltip content="Add a zoom at the playhead" {...props}>
				<button type="button">Zoom</button>
			</Tooltip>
		</TooltipProvider>,
	);
	return screen.getByRole("button", { name: "Zoom" });
}

// Radix draws the visible tooltip and a visually hidden `role="tooltip"` copy for assistive
// technology, so the styled node is found by its slot.
function visibleTooltip() {
	return document.querySelector<HTMLElement>('[data-slot="tooltip-content"]');
}

describe("Tooltip", () => {
	it("wraps long text and follows the text's own direction", () => {
		const button = renderTooltip();
		act(() => button.focus());

		const content = visibleTooltip();
		expect(content).toHaveAttribute("dir", "auto");
		expect(content?.className).toContain("max-w-[260px]");
		expect(content).toHaveTextContent("Add a zoom at the playhead");
	});

	it("renders a shortcut as its own left-to-right chip after the text", () => {
		const button = renderTooltip({ shortcut: "Ctrl + Z" });
		act(() => button.focus());

		const chip = visibleTooltip()?.querySelector("kbd");
		expect(chip).toHaveTextContent("Ctrl + Z");
		expect(chip).toHaveAttribute("dir", "ltr");
		// The chip is a sibling of the text, not part of the translated string.
		expect(chip?.previousSibling?.textContent).toBe("Add a zoom at the playhead");
	});

	it("draws no chip when there is no shortcut", () => {
		const button = renderTooltip();
		act(() => button.focus());

		expect(visibleTooltip()?.querySelector("kbd")).toBeNull();
	});

	it("opens 400 ms after the pointer arrives, not before", () => {
		vi.useFakeTimers();
		const button = renderTooltip();

		fireEvent.pointerMove(button);
		act(() => {
			vi.advanceTimersByTime(399);
		});
		expect(visibleTooltip()).toBeNull();

		act(() => {
			vi.advanceTimersByTime(1);
		});
		expect(visibleTooltip()).not.toBeNull();
	});

	it("opens at once on keyboard focus and describes the trigger", () => {
		const button = renderTooltip();
		act(() => button.focus());

		expect(visibleTooltip()).not.toBeNull();
		expect(button).toHaveAccessibleDescription("Add a zoom at the playhead");
	});
});
