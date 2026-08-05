import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";

import type { PipelineExecutionView } from "../../api/types";
import type { FileSection } from "../../page/files";
import { mono, paper } from "../../theme";
import ExecutionList from "./ExecutionList";
import FileList from "./FileList";

/**
 * The left panel: what has been run, what the page now holds, and the way into
 * the log.
 *
 * The two halves are deliberately not the same list. Executions are the history
 * of the page; *Files* are its present contents, and a later execution may have
 * overwritten what an earlier one wrote. Presenting the second as a tree under
 * the first would put one path under two headings and make one of them wrong.
 */
export default function OverviewPanel({
  executions,
  sections,
  selectedKey,
  onSelect,
  onDownload,
  logLineCount,
  onToggleLog,
}: {
  executions: PipelineExecutionView[];
  sections: FileSection[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  onDownload: (paths: string[]) => void;
  logLineCount: number;
  onToggleLog: () => void;
}) {
  return (
    <Box
      sx={{
        // The design says 300; twenty more is what `{s}/transcription.musicxml`
        // needs to be read rather than guessed at, and pixel widths in the
        // handoff are intent rather than law.
        width: 320,
        flex: "none",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        borderRight: `1px solid ${paper["200"]}`,
        bgcolor: paper["050"],
      }}
    >
      <Box sx={{ borderBottom: `1px solid ${paper["200"]}` }}>
        <Box sx={{ px: 2.25, pt: 1.75, pb: 1 }}>
          <SectionLabel>Executions</SectionLabel>
        </Box>
        <ExecutionList executions={executions} />
      </Box>

      <Box sx={{ px: 2.25, pt: 1.75, pb: 1.25, borderBottom: `1px solid ${paper["200"]}` }}>
        <SectionLabel>Files</SectionLabel>
        <Box sx={{ mt: 0.625, fontSize: "0.78125rem", lineHeight: 1.5, color: paper["500"] }}>
          Click one to show only that layer.
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: "auto", minHeight: 0 }}>
        <FileList
          sections={sections}
          selectedKey={selectedKey}
          onSelect={onSelect}
          onDownload={onDownload}
        />
      </Box>

      <Box sx={{ borderTop: `1px solid ${paper["200"]}`, p: 1.5 }}>
        <ButtonBase
          onClick={onToggleLog}
          sx={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            border: `1px solid ${paper["200"]}`,
            borderRadius: "20px",
            bgcolor: paper["100"],
            color: paper["600"],
            fontFamily: mono,
            fontSize: "0.75rem",
            lineHeight: 1,
            px: 1.75,
            py: 1,
            "&:hover": { bgcolor: paper["150"] },
          }}
        >
          <span>Recognition log</span>
          <Box component="span" sx={{ color: paper["500"] }}>
            {logLineCount} lines ›
          </Box>
        </ButtonBase>
      </Box>
    </Box>
  );
}

function SectionLabel({ children }: { children: string }) {
  return (
    <Box
      sx={{
        fontFamily: mono,
        fontWeight: 600,
        fontSize: "0.6875rem",
        lineHeight: 1,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: paper["600"],
      }}
    >
      {children}
    </Box>
  );
}
