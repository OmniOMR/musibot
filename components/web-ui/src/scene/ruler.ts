import { axisBottom, axisLeft } from "d3-axis";
import { scaleLinear } from "d3-scale";
import { select } from "d3-selection";

import { mono, paper } from "../theme";
import type { Transform, Viewport } from "./useZoom";

/**
 * The pixel rulers down the left and along the bottom of the canvas.
 *
 * A scale bar answers the question the zoom percentage cannot: *how big is
 * this thing*. A staff is around a hundred pixels tall in the scan and a
 * notehead around twenty, and being able to read that off the edge of the
 * canvas is worth more than knowing the view is at 340%.
 *
 * This is the one part of the app d3 renders itself, into a `<g>` that React
 * creates empty and never puts children into. That division has to hold: React
 * would have nothing to diff there, so it leaves the subtree alone, and d3 is
 * free to own it. Give that `<g>` a React child and the two will fight over the
 * same DOM.
 *
 * It is imperative because it has to update on every frame of a pan, and the
 * transform is deliberately not React state — see `useZoom`. Re-calling an axis
 * is cheap and idempotent: d3 has enter/update/exit inside it, so this can run
 * sixty times a second and under a double-invoked effect without accumulating
 * anything.
 */
export interface Ruler {
  update: (transform: Transform, viewport: Viewport) => void;
}

/** Roughly how far apart ticks should sit on screen, in pixels. */
const TICK_SPACING = 90;

/**
 * Where the axes sit, far enough in for their own labels to fit — and the width
 * of the translucent strip the panel draws under them, since the two are the
 * same band and drift apart the moment they are written down twice.
 */
export const RULER_GUTTER = 44;

const GUTTER = RULER_GUTTER;

export function createRuler(bottom: SVGGElement, left: SVGGElement): Ruler {
  return {
    update(transform: Transform, viewport: Viewport) {
      // World coordinates are image pixels. These scales map the part of that
      // space currently on screen onto the screen, which is exactly what the
      // zoom transform does — written as a scale so that d3 can pick tick
      // intervals that stay round as the view moves.
      const x = scaleLinear()
        .domain([-transform.x / transform.k, (viewport.width - transform.x) / transform.k])
        .range([0, viewport.width]);

      const y = scaleLinear()
        .domain([-transform.y / transform.k, (viewport.height - transform.y) / transform.k])
        .range([0, viewport.height]);

      select(bottom)
        .attr("transform", `translate(0, ${viewport.height - GUTTER})`)
        .call(
          axisBottom(x)
            .ticks(Math.max(2, Math.round(viewport.width / TICK_SPACING)))
            .tickSize(4)
            .tickPadding(4),
        )
        .call(style);

      select(left)
        .attr("transform", `translate(${GUTTER}, 0)`)
        .call(
          axisLeft(y)
            .ticks(Math.max(2, Math.round(viewport.height / TICK_SPACING)))
            .tickSize(4)
            .tickPadding(4),
        )
        .call(style);
    },
  };
}

/**
 * The theme, applied by hand.
 *
 * An imperative island does not get `sx`, so the tokens are set as attributes.
 * They are the same tokens the rest of the panel uses — a ruler that drifted
 * from the type scale would be the tell that something here is not React.
 */
function style(selection: ReturnType<typeof select<SVGGElement, unknown>>): void {
  selection
    .selectAll("text")
    .attr("fill", paper["500"])
    .attr("font-family", mono)
    .attr("font-size", 10);
  selection.selectAll("line").attr("stroke", paper["300"]);
  selection.selectAll("path.domain").attr("stroke", paper["300"]);
}
