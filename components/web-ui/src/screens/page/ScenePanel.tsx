import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import CircularProgress from "@mui/material/CircularProgress";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { FileView } from "../../api/types";
import type { FileRow } from "../../page/files";
import type { CocoLayer } from "../../scene/coco";
import { createRuler, RULER_GUTTER, type Ruler } from "../../scene/ruler";
import { instanceLabel, pathsOf, sceneFor, type Plate } from "../../scene/scene";
import { useSceneData, type SceneImage } from "../../scene/useSceneData";
import { useZoom, type Bounds, type Transform, type Viewport } from "../../scene/useZoom";
import { mono, paper } from "../../theme";

/**
 * The canvas: the scan, and whatever has been found on it.
 *
 * Two spaces meet here and keeping them apart is the whole design.
 *
 * **World space** is image pixels. The plates and every box sit in it, React
 * renders them, and they change only when the selected layer changes — never
 * while somebody is panning. The transform that moves them is written straight
 * onto one `<g>` through a ref, so a gesture reaches no React component at all.
 *
 * **Screen space** is the viewport. The rulers and the staff labels live there,
 * so they are recomputed every frame; since the transform is deliberately not
 * React state, they are driven from the same callback that moves the world.
 * That is why they are imperative — there is no state change for them to react
 * to. A box's stroke belongs to screen space too, and SVG solves that one for
 * free with `vector-effect`.
 */
export default function ScenePanel({
  pageId,
  token,
  selected,
  files,
}: {
  pageId: string;
  token: string | null;
  selected: FileRow | null;
  files: FileView[];
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const worldRef = useRef<SVGGElement | null>(null);
  const labelsRef = useRef<SVGGElement | null>(null);
  const rulerBottomRef = useRef<SVGGElement | null>(null);
  const rulerLeftRef = useRef<SVGGElement | null>(null);
  const ruler = useRef<Ruler | null>(null);

  const [viewport, setViewport] = useState<Viewport>({ width: 0, height: 0 });
  /** Mirrored out of the transform for the toolbar alone, once per frame. */
  const [zoomPercent, setZoomPercent] = useState(100);
  const [hovered, setHovered] = useState<string | null>(null);

  // The transform callback runs outside React and cannot read state, so what it
  // needs is mirrored into refs.
  const viewportRef = useRef<Viewport>(viewport);
  viewportRef.current = viewport;

  // Two passes over the same function. The first, with no sizes, is only asked
  // what to fetch — which does not depend on how big anything is. The second
  // places the plates once the images have been measured. The paths are
  // identical both times, so nothing is fetched twice and there is no loop.
  const scene = useMemo(() => sceneFor(selected, files, new Map()), [selected, files]);
  const paths = useMemo(() => pathsOf(scene), [scene]);
  const data = useSceneData(pageId, token, paths, files);

  const placed = useMemo(
    () =>
      sceneFor(
        selected,
        files,
        new Map([...data.images].map(([path, image]) => [path, image.height])),
      ),
    [selected, files, data.images],
  );

  const applyTransform = useCallback((transform: Transform) => {
    worldRef.current?.setAttribute(
      "transform",
      `translate(${transform.x},${transform.y}) scale(${transform.k})`,
    );
    // Labels sit at world coordinates but must not grow with the image, so each
    // carries the inverse of the current scale. A dozen attribute writes.
    const inverse = `scale(${1 / transform.k})`;
    for (const label of labelsRef.current?.querySelectorAll("[data-counter-scale]") ?? []) {
      label.setAttribute("transform", inverse);
    }

    // Magnified, the scan is drawn pixel for pixel rather than smoothed: a
    // model developer looking closely is looking at exactly the pixels the
    // model was given, and interpolation invents detail that was never there.
    // Reduced, it goes back to the browser's own filtering — nearest-neighbour
    // minification drops rows and columns outright, which turns staff lines
    // into a moiré. The switch is at 1:1, where the two produce the same image
    // and the change cannot be seen happening.
    const rendering = transform.k >= 1 ? "pixelated" : "auto";
    for (const image of worldRef.current?.querySelectorAll("image") ?? []) {
      image.style.imageRendering = rendering;
    }
    ruler.current?.update(transform, viewportRef.current);
    setZoomPercent(Math.round(transform.k * 100));
  }, []);

  const { zoomBy, fit, current } = useZoom(svgRef, applyTransform);

  useLayoutEffect(() => {
    if (rulerBottomRef.current !== null && rulerLeftRef.current !== null) {
      ruler.current = createRuler(rulerBottomRef.current, rulerLeftRef.current);
      ruler.current.update(current(), viewport);
    }
  }, [current, viewport]);

  /**
   * Re-apply the transform after React has rendered a new scene.
   *
   * The counter-scale on each label is written by `applyTransform`, which only
   * runs when a zoom event fires. React can hand us freshly created labels with
   * no such event behind them — switching from a staff's images to that same
   * staff's detections keeps the plates identical, so nothing re-frames and
   * nothing zooms — and those labels would render at world scale, which at a
   * fitted zoom is an illegible speck.
   */
  useLayoutEffect(() => {
    applyTransform(current());
  }, [placed, data.images, applyTransform, current]);

  // The panel's size is not knowable from React, and it changes when the
  // transcription panel appears beside it.
  useEffect(() => {
    const svg = svgRef.current;
    if (svg === null) {
      return;
    }
    const observer = new ResizeObserver(() => {
      setViewport({ width: svg.clientWidth, height: svg.clientHeight });
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);

  const bounds = useMemo(() => boundsOf(placed.plates, data.images), [placed, data.images]);

  /**
   * Frame the scene when what is on it changes.
   *
   * A selection is a request to look at something, and starting wherever the
   * previous layer happened to be panned to is not looking at it. Keyed by the
   * plates *and* their measured sizes, so the first frame after the images
   * arrive is the one that lands.
   */
  const framed = useRef("");
  useEffect(() => {
    if (bounds === null || viewport.width === 0) {
      return;
    }
    const key = placed.plates
      .map((plate) => `${plate.path}:${data.images.get(plate.path)?.height ?? 0}`)
      .join("|");
    if (key !== "" && key !== framed.current) {
      framed.current = key;
      fit(bounds, viewport);
    }
  }, [bounds, viewport, placed, data.images, fit]);

  return (
    <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <Toolbar
        showing={selected === null ? null : placed.description}
        zoomPercent={zoomPercent}
        onZoomIn={() => zoomBy(1.4)}
        onZoomOut={() => zoomBy(1 / 1.4)}
        onFit={() => bounds !== null && fit(bounds, viewport)}
        canFit={bounds !== null}
      />

      <Box sx={{ flex: 1, position: "relative", minHeight: 0, bgcolor: paper["150"] }}>
        <Box
          component="svg"
          ref={svgRef}
          sx={{
            width: "100%",
            height: "100%",
            display: "block",
            cursor: "grab",
            touchAction: "none",
            "&:active": { cursor: "grabbing" },
          }}
        >
          <g ref={worldRef}>
            {placed.plates.map((plate) => (
              <PlateView
                key={plate.path}
                plate={plate}
                image={data.images.get(plate.path)}
                overlay={
                  plate.overlayPath === null ? undefined : data.overlays.get(plate.overlayPath)
                }
                colour={placed.overlayColour}
                onHoverBox={setHovered}
              />
            ))}

            {/* Inside the world group, so the transform places them; each label
                then undoes the scale so its type stays the size it was drawn.
                Outside it they would be positioned in raw SVG coordinates and
                land wherever the viewport happened to start. */}
            <g ref={labelsRef}>
              {placed.plates.map((plate) => {
                const image = data.images.get(plate.path);
                if (plate.instance === null || image === undefined) {
                  return null;
                }
                // Outer group: where the label belongs, in world coordinates, set
                // once by React. Inner group: the inverse scale, rewritten every
                // frame so the text keeps its size.
                return (
                  <g
                    key={plate.path}
                    transform={`translate(${plate.x},${plate.y + image.height / 2})`}
                  >
                    <g data-counter-scale="">
                      <text
                        x={-10}
                        y={0}
                        textAnchor="end"
                        dominantBaseline="middle"
                        fontFamily={mono}
                        fontSize={11}
                        fontWeight={600}
                        fill={placed.overlayColour ?? paper["600"]}
                      >
                        {instanceLabel(plate.path)}
                      </text>
                    </g>
                  </g>
                );
              })}
            </g>
          </g>

          {/* The rulers' bodies: translucent white, like the plastic ones, so
              that ticks and figures lift off a dark scan without hiding it.
              Half opacity is a judgement made by looking rather than by
              measuring — more of it reads the ticks better, but two bright
              bands then pull the eye away from the page they are measuring,
              which is the wrong thing for a ruler to do.

              Drawn in React rather than by d3: they change with the viewport,
              not with the transform. The two strips tile rather than overlap,
              or the corner would stack two layers of white and read as a
              seam. */}
          <g pointerEvents="none">
            <rect
              x={0}
              y={viewport.height - RULER_GUTTER}
              width={viewport.width}
              height={RULER_GUTTER}
              fill={paper["000"]}
              fillOpacity={0.5}
            />
            <rect
              x={0}
              y={0}
              width={RULER_GUTTER}
              height={Math.max(viewport.height - RULER_GUTTER, 0)}
              fill={paper["000"]}
              fillOpacity={0.5}
            />
            {/* The edges the measurements are read against. */}
            <line
              x1={0}
              y1={viewport.height - RULER_GUTTER}
              x2={viewport.width}
              y2={viewport.height - RULER_GUTTER}
              stroke={paper["300"]}
            />
            <line
              x1={RULER_GUTTER}
              y1={0}
              x2={RULER_GUTTER}
              y2={viewport.height - RULER_GUTTER}
              stroke={paper["300"]}
            />
          </g>

          {/* d3 owns these two. They must never gain a React child. */}
          <g ref={rulerBottomRef} />
          <g ref={rulerLeftRef} />
        </Box>

        {data.loading && (
          <Centred>
            <CircularProgress size={20} />
          </Centred>
        )}
        {selected === null && <Centred>Choose a file on the left to see it.</Centred>}
        {placed.empty !== null && <Centred>{placed.empty}</Centred>}
        {data.error !== null && <Centred>{data.error}</Centred>}

        {hovered !== null && (
          <Box
            sx={{
              position: "absolute",
              left: 12,
              top: 12,
              px: 1.25,
              py: 0.75,
              bgcolor: paper["950"],
              color: paper["050"],
              borderRadius: 1,
              fontFamily: mono,
              fontSize: "0.75rem",
              pointerEvents: "none",
            }}
          >
            {hovered}
          </Box>
        )}
      </Box>
    </Box>
  );
}

function Centred({ children }: { children: React.ReactNode }) {
  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        pointerEvents: "none",
        color: paper["600"],
        fontSize: "0.875rem",
        textAlign: "center",
        px: 3,
      }}
    >
      {children}
    </Box>
  );
}

/**
 * One image and the boxes over it.
 *
 * Memoised, and that is what the whole arrangement is for: a pan writes one
 * attribute on the world `<g>` and never reaches here, so a thousand boxes cost
 * nothing to move.
 */
const PlateView = memo(function PlateView({
  plate,
  image,
  overlay,
  colour,
  onHoverBox,
}: {
  plate: Plate;
  image: SceneImage | undefined;
  overlay: CocoLayer | undefined;
  colour: string | null;
  onHoverBox: (label: string | null) => void;
}) {
  if (image === undefined) {
    return null;
  }

  return (
    <g transform={`translate(${plate.x},${plate.y})`}>
      <image href={image.url} width={image.width} height={image.height} />
      <rect
        x={0}
        y={0}
        width={image.width}
        height={image.height}
        fill="none"
        stroke={paper["300"]}
        vectorEffect="non-scaling-stroke"
      />
      {colour !== null &&
        overlay?.boxes.map((box) => (
          <rect
            key={box.id}
            x={box.x}
            y={box.y}
            width={box.width}
            height={box.height}
            fill="none"
            stroke={colour}
            // Screen space, solved by SVG rather than by a frame callback: a
            // one-pixel stroke stays one pixel at 400%.
            vectorEffect="non-scaling-stroke"
            onMouseEnter={box.label === null ? undefined : () => onHoverBox(box.label)}
            onMouseLeave={box.label === null ? undefined : () => onHoverBox(null)}
          />
        ))}
    </g>
  );
});

function Toolbar({
  showing,
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onFit,
  canFit,
}: {
  showing: string | null;
  zoomPercent: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  canFit: boolean;
}) {
  return (
    <Box
      sx={{
        height: 46,
        flex: "none",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 2,
        px: 2,
        borderBottom: `1px solid ${paper["200"]}`,
        bgcolor: paper["050"],
      }}
    >
      <Box
        sx={{
          fontSize: "0.78125rem",
          color: paper["600"],
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          lineHeight: 1.6,
        }}
      >
        Showing{" "}
        <Box
          component="strong"
          sx={{
            color: paper["900"],
            fontWeight: 600,
            fontFamily: showing === null ? undefined : mono,
          }}
        >
          {showing ?? "nothing yet"}
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flex: "none" }}>
        <ZoomButton label="Zoom out" onClick={onZoomOut}>
          −
        </ZoomButton>
        <Box
          sx={{
            fontFamily: mono,
            fontSize: "0.75rem",
            color: paper["600"],
            minWidth: 44,
            textAlign: "center",
          }}
        >
          {zoomPercent}%
        </Box>
        <ZoomButton label="Zoom in" onClick={onZoomIn}>
          +
        </ZoomButton>
        <ButtonBase
          disabled={!canFit}
          onClick={onFit}
          sx={{
            ml: 0.75,
            border: `1px solid ${paper["300"]}`,
            borderRadius: 1.5,
            bgcolor: paper["000"],
            color: paper["900"],
            fontWeight: 600,
            fontSize: "0.75rem",
            px: 1.25,
            py: 0.875,
            "&:hover": { bgcolor: paper["100"] },
            "&.Mui-disabled": { opacity: 0.5 },
          }}
        >
          Fit
        </ButtonBase>
      </Box>
    </Box>
  );
}

function ZoomButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <ButtonBase
      aria-label={label}
      onClick={onClick}
      sx={{
        width: 28,
        height: 28,
        border: `1px solid ${paper["300"]}`,
        borderRadius: 1.5,
        bgcolor: paper["000"],
        color: paper["900"],
        fontSize: "0.9375rem",
        lineHeight: 1,
        "&:hover": { bgcolor: paper["100"] },
      }}
    >
      {children}
    </ButtonBase>
  );
}

/** The world-space rectangle every plate fits inside. */
function boundsOf(plates: Plate[], images: Map<string, SceneImage>): Bounds | null {
  const measured = plates.filter((plate) => images.has(plate.path));
  if (measured.length === 0) {
    return null;
  }
  const right = measured.reduce(
    (widest, plate) => Math.max(widest, plate.x + (images.get(plate.path)?.width ?? 0)),
    0,
  );
  const bottom = measured.reduce(
    (lowest, plate) => Math.max(lowest, plate.y + (images.get(plate.path)?.height ?? 0)),
    0,
  );
  return { x: 0, y: 0, width: Math.max(right, 1), height: Math.max(bottom, 1) };
}
