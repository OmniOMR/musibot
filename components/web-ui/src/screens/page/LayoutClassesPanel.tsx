import FiberManualRecord from "@mui/icons-material/FiberManualRecord";
import FiberManualRecordOutlined from "@mui/icons-material/FiberManualRecordOutlined";
import VisibilityOffOutlined from "@mui/icons-material/VisibilityOffOutlined";
import VisibilityOutlined from "@mui/icons-material/VisibilityOutlined";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { useMemo } from "react";

import type { FileView } from "../../api/types";
import type { FileRow } from "../../page/files";
import { classesIn, solo, styleOf, type ClassCount } from "../../scene/layoutClasses";
import { useSceneData } from "../../scene/useSceneData";
import { mono, paper } from "../../theme";

/**
 * Which kinds of box the canvas draws, for a `layout.json`.
 *
 * Present only while a layout is selected, in the place the reading takes for a
 * transcription. A page's layout is a few systems, a dozen staves and a few
 * hundred measures, and drawn all at once they hide the scan they are about —
 * so every class can be switched off, or soloed to see it alone, and each says
 * how many of it there are, which is often the question somebody opened the
 * file to answer.
 *
 * Narrow rather than half the width, unlike the reading: it is a list of a few
 * names, and the canvas is still the thing being looked at.
 */
export default function LayoutClassesPanel({
  pageId,
  token,
  selected,
  files,
  hidden,
  onChange,
}: {
  pageId: string;
  token: string | null;
  selected: FileRow | null;
  files: FileView[];
  hidden: ReadonlySet<string>;
  onChange: (hidden: Set<string>) => void;
}) {
  // The same files the canvas reads, fetched again: a `layout.json` is a few
  // kilobytes, and sharing the canvas's buffer would couple two panels that
  // otherwise know nothing of each other.
  const paths = useMemo(() => selected?.paths ?? [], [selected]);
  const data = useSceneData(pageId, token, paths, files);
  const classes = useMemo(() => classesIn([...data.overlays.values()]), [data.overlays]);
  const names = classes.map(({ name }) => name);

  function toggle(name: string) {
    const next = new Set(hidden);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    onChange(next);
  }

  return (
    <Box
      sx={{
        width: 264,
        flex: "none",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        borderLeft: `1px solid ${paper["200"]}`,
        bgcolor: paper["050"],
      }}
    >
      <Box
        sx={{
          height: 46,
          flex: "none",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          px: 2,
          borderBottom: `1px solid ${paper["200"]}`,
          fontSize: "0.78125rem",
          color: paper["600"],
        }}
      >
        Classes
      </Box>

      <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", py: 0.75 }}>
        {data.loading && classes.length === 0 ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={20} />
          </Box>
        ) : classes.length === 0 && data.error === null ? (
          <Box sx={{ px: 2, py: 2, fontSize: "0.8125rem", color: paper["600"] }}>
            This layout has no boxes in it.
          </Box>
        ) : (
          classes.map((entry) => (
            <ClassRow
              key={entry.name}
              entry={entry}
              shown={!hidden.has(entry.name)}
              alone={names.every((name) => (name === entry.name) !== hidden.has(name))}
              onToggle={() => toggle(entry.name)}
              onSolo={() => onChange(solo(entry.name, names, hidden))}
            />
          ))
        )}

        {data.error !== null && (
          <Box sx={{ px: 2, py: 2, fontSize: "0.8125rem", color: paper["600"] }}>{data.error}</Box>
        )}
      </Box>
    </Box>
  );
}

function ClassRow({
  entry,
  shown,
  alone,
  onToggle,
  onSolo,
}: {
  entry: ClassCount;
  shown: boolean;
  /** Whether this is the only class showing, which is what soloing it does. */
  alone: boolean;
  onToggle: () => void;
  onSolo: () => void;
}) {
  const style = styleOf(entry.name);

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 0.75,
        pl: 0.75,
        pr: 1,
        py: 0.25,
        // A hidden class stays in the list, dimmed rather than removed, so it
        // can be switched back on where it was.
        color: shown ? paper["900"] : paper["400"],
      }}
    >
      {/* Tooltips to the left and never under the pointer: below, they would
          cover the next row's buttons just as somebody reached for them. */}
      <Tooltip title={shown ? "Hide" : "Show"} placement="left" disableInteractive>
        <IconButton
          size="small"
          onClick={onToggle}
          aria-label={`${shown ? "Hide" : "Show"} ${entry.name}`}
          aria-pressed={shown}
          sx={{ color: "inherit" }}
        >
          {shown ? (
            <VisibilityOutlined fontSize="small" />
          ) : (
            <VisibilityOffOutlined fontSize="small" />
          )}
        </IconButton>
      </Tooltip>

      {/* The box as the canvas draws it, so the list is its own legend. */}
      <Box
        aria-hidden
        sx={{
          width: 14,
          height: 14,
          flex: "none",
          boxSizing: "border-box",
          border: `2px ${style.dashed ? "dashed" : "solid"} ${style.colour}`,
          bgcolor: `${style.colour}22`,
          opacity: shown ? 1 : 0.4,
        }}
      />

      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          fontFamily: mono,
          fontSize: "0.78125rem",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={entry.name}
      >
        {entry.name}
      </Box>

      <Box
        sx={{
          fontFamily: mono,
          fontSize: "0.75rem",
          color: shown ? paper["600"] : paper["400"],
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {entry.count}×
      </Box>

      <Tooltip title={alone ? "Show all" : "Show only this"} placement="left" disableInteractive>
        <IconButton
          size="small"
          onClick={onSolo}
          aria-label={alone ? "Show all classes" : `Show only ${entry.name}`}
          aria-pressed={alone}
          sx={{ color: alone ? paper["900"] : paper["400"] }}
        >
          {alone ? (
            <FiberManualRecord sx={{ fontSize: 14 }} />
          ) : (
            <FiberManualRecordOutlined sx={{ fontSize: 14 }} />
          )}
        </IconButton>
      </Tooltip>
    </Box>
  );
}
