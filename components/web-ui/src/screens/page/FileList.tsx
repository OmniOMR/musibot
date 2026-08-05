import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";

import { formatSize, type FileSection } from "../../page/files";
import { cuni, mono, paper } from "../../theme";

/**
 * The page's *Files*, and the layer switcher.
 *
 * Selecting a row is how the canvas is told what to show, which is why there is
 * no legend anywhere: one layer is displayed at a time and its name is in the
 * toolbar. Rows are the page's actual contents rather than any execution's
 * outputs — see `page/files.ts` for why that distinction matters.
 *
 * The download arrow is absent on the file the visitor uploaded. They have it;
 * offering it back is the one row where the arrow means nothing.
 */
export default function FileList({
  sections,
  selectedKey,
  onSelect,
  onDownload,
}: {
  sections: FileSection[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  onDownload: (paths: string[]) => void;
}) {
  if (sections.length === 0) {
    return (
      <Box sx={{ px: 2.25, py: 1.5, fontSize: "0.75rem", color: paper["500"] }}>
        Nothing has been written to this page yet.
      </Box>
    );
  }

  return (
    <>
      {sections.map((section) => (
        <Box key={section.heading}>
          <Box
            sx={{
              px: 2.25,
              pt: 1.75,
              pb: 0.75,
              fontWeight: 600,
              fontSize: "0.75rem",
              lineHeight: 1.3,
              color: paper["950"],
            }}
          >
            {section.heading}
          </Box>

          {section.rows.map((row) => {
            const selected = row.key === selectedKey;
            return (
              <Box
                key={row.key}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.25,
                  pr: 2.25,
                  // Selection goes *darker* than the panel, not lighter: the
                  // ramp is 050 for the panel, 100 under the pointer and 150
                  // for the row that is chosen, so hovering never looks more
                  // selected than the selection.
                  bgcolor: selected ? paper["150"] : "transparent",
                  borderLeft: `2px solid ${selected ? cuni.red : "transparent"}`,
                  "&:hover": { bgcolor: selected ? paper["150"] : paper["100"] },
                }}
              >
                <ButtonBase
                  onClick={() => onSelect(row.key)}
                  sx={{
                    flex: 1,
                    minWidth: 0,
                    display: "flex",
                    justifyContent: "flex-start",
                    alignItems: "center",
                    gap: 1.25,
                    textAlign: "left",
                    pl: 2,
                    py: 1.125,
                  }}
                >
                  <Box
                    aria-hidden
                    sx={{
                      flex: "none",
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      bgcolor: row.willBeOverwritten ? cuni.red : paper["700"],
                    }}
                  />
                  {/* The folders give way and the file name stays: cutting the
                      tail would hide the only thing separating
                      `…/transcription.musicxml` from `…/transcription.lmx`. */}
                  <Box
                    title={row.label}
                    sx={{
                      flex: 1,
                      minWidth: 0,
                      display: "flex",
                      fontFamily: mono,
                      fontSize: "0.78125rem",
                      lineHeight: 1.4,
                      color: paper["900"],
                    }}
                  >
                    <Box
                      component="span"
                      sx={{
                        // An enormous shrink factor, so the folders give up
                        // their width first and collapse to nothing rather than
                        // leaving a sliver of a clipped character behind.
                        flex: "0 9999 auto",
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        color: paper["600"],
                      }}
                    >
                      {row.prefix}
                    </Box>
                    <Box component="span" sx={{ flex: "none" }}>
                      {row.name}
                    </Box>
                  </Box>
                  <Box
                    sx={{
                      flex: "none",
                      fontFamily: mono,
                      fontSize: "0.71875rem",
                      lineHeight: 1,
                      color: row.willBeOverwritten ? cuni.redDark : paper["600"],
                    }}
                  >
                    {noteFor(row)}
                  </Box>
                </ButtonBase>

                {!row.isSource && (
                  <Tooltip
                    title={`Download ${row.paths.length === 1 ? "" : `${row.paths.length} files`}`.trim()}
                  >
                    <ButtonBase
                      aria-label={`Download ${row.label}`}
                      onClick={() => onDownload(row.paths)}
                      sx={{
                        flex: "none",
                        px: 0.5,
                        fontSize: "0.8125rem",
                        color: paper["400"],
                        "&:hover": { color: paper["700"] },
                      }}
                    >
                      ↓
                    </ButtonBase>
                  </Tooltip>
                )}
              </Box>
            );
          })}
        </Box>
      ))}
    </>
  );
}

/**
 * The one thing worth saying to the right of the name.
 *
 * "will be replaced" outranks everything: a visitor about to download a file
 * that a running execution is going to overwrite should hear it before they
 * click, not after.
 */
function noteFor(row: {
  willBeOverwritten: boolean;
  instances: number | null;
  size: number;
}): string {
  if (row.willBeOverwritten) {
    return "will be replaced";
  }
  if (row.instances !== null && row.instances > 1) {
    return `${row.instances}×`;
  }
  return formatSize(row.size);
}
