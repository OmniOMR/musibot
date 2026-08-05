import { select } from "d3-selection";
import { zoom as d3Zoom, zoomIdentity, type D3ZoomEvent, type ZoomBehavior } from "d3-zoom";
import { useCallback, useEffect, useRef } from "react";

/**
 * Panning and zooming, deliberately outside React's state.
 *
 * This is the one place in the app that runs on every animation frame, and the
 * decision that shapes it is that **the transform is never React state**. Put
 * it there and each frame of a drag re-renders the panel and walks every box in
 * the scene to confirm it has not changed — a thousand of them, sixty times a
 * second, to move one attribute. Instead the transform is written straight onto
 * the world `<g>` through a ref, so a gesture costs React exactly nothing and
 * the boxes inside re-render only when the layer they belong to changes.
 *
 * Everything else that lives in *screen* space rather than world space — the
 * ruler, the staff labels, the zoom percentage — follows from that same
 * decision: there is no state change per frame for them to react to, so they
 * are updated from `onTransform` too. That is why they are imperative, not
 * because React would be too slow for a dozen ticks.
 *
 * d3 supplies the behaviour and owns no DOM inside React's tree. What it is
 * worth having is the part nobody wants to write twice: wheel normalisation
 * across browsers, trackpad pinch, touch, and clamping.
 */
export interface Transform {
  k: number;
  x: number;
  y: number;
}

export interface Viewport {
  width: number;
  height: number;
}

/** A rectangle in world coordinates. */
export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

const SCALE_EXTENT: [number, number] = [0.02, 40];

/**
 * Room left around the scene when it is framed.
 *
 * Not symmetric, because the edges are not: the left one carries the vertical
 * ruler *and* the crop labels that hang off each plate, and the bottom carries
 * the horizontal ruler. Fitting to equal margins puts the labels underneath the
 * ruler, where they are invisible and look like a bug rather than a collision.
 */
const FIT_PADDING = { top: 32, right: 32, bottom: 56, left: 120 };

export interface ZoomControls {
  /** Multiply the current scale, about the centre of the viewport. */
  zoomBy: (factor: number) => void;
  /** Frame these world bounds in the viewport. */
  fit: (bounds: Bounds, viewport: Viewport) => void;
  /** The transform right now, for a caller that needs it outside a frame. */
  current: () => Transform;
}

export function useZoom(
  svgRef: React.RefObject<SVGSVGElement | null>,
  onTransform: (transform: Transform) => void,
): ZoomControls {
  const behaviour = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const transform = useRef<Transform>({ k: 1, x: 0, y: 0 });

  // Held in a ref so that changing the callback does not tear down and rebuild
  // the behaviour, which would drop any gesture in progress.
  const notify = useRef(onTransform);
  notify.current = onTransform;

  useEffect(() => {
    const svg = svgRef.current;
    if (svg === null) {
      return;
    }

    const behave = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent(SCALE_EXTENT)
      .on("zoom", (event: D3ZoomEvent<SVGSVGElement, unknown>) => {
        transform.current = { k: event.transform.k, x: event.transform.x, y: event.transform.y };
        notify.current(transform.current);
      });

    behaviour.current = behave;
    const selection = select(svg);
    selection.call(behave);
    // The browser's own double-click-to-zoom fights a canvas where a
    // double-click is how you look closer at one thing.
    selection.on("dblclick.zoom", null);

    return () => {
      selection.on(".zoom", null);
      behaviour.current = null;
    };
  }, [svgRef]);

  const zoomBy = useCallback(
    (factor: number) => {
      const svg = svgRef.current;
      if (svg === null || behaviour.current === null) {
        return;
      }
      behaviour.current.scaleBy(select(svg), factor);
    },
    [svgRef],
  );

  const fit = useCallback(
    (bounds: Bounds, viewport: Viewport) => {
      const svg = svgRef.current;
      if (svg === null || behaviour.current === null) {
        return;
      }
      if (bounds.width <= 0 || bounds.height <= 0 || viewport.width <= 0 || viewport.height <= 0) {
        return;
      }

      const inner = {
        width: viewport.width - FIT_PADDING.left - FIT_PADDING.right,
        height: viewport.height - FIT_PADDING.top - FIT_PADDING.bottom,
      };
      if (inner.width <= 0 || inner.height <= 0) {
        return;
      }

      const scale = Math.min(inner.width / bounds.width, inner.height / bounds.height);
      const k = Math.min(Math.max(scale, SCALE_EXTENT[0]), SCALE_EXTENT[1]);

      // Centred within the padded box rather than within the viewport, so the
      // asymmetry actually moves the scene rather than only shrinking it.
      behaviour.current.transform(
        select(svg),
        zoomIdentity
          .translate(
            FIT_PADDING.left + inner.width / 2 - (bounds.x + bounds.width / 2) * k,
            FIT_PADDING.top + inner.height / 2 - (bounds.y + bounds.height / 2) * k,
          )
          .scale(k),
      );
    },
    [svgRef],
  );

  const current = useCallback(() => transform.current, []);

  return { zoomBy, fit, current };
}
