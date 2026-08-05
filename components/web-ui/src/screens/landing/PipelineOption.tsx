import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";

import { cuni, paper } from "../../theme";

/**
 * One of the two choices a visitor is actually offered: a whole page, or a
 * single staff.
 *
 * A radio in behaviour and in the accessibility tree, but drawn rather than
 * rendered with `Radio` — the design puts the control inside a bordered card
 * whose whole surface is the target, and the border going red is the selection
 * indicator as much as the dot is.
 *
 * Disabled when the *Pipeline* behind it is not deployed on this instance,
 * which is not rare: the two defaults are named by this app and announced by
 * whatever happens to be connected.
 */
export default function PipelineOption({
  title,
  description,
  selected,
  disabled,
  onSelect,
}: {
  title: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <ButtonBase
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      sx={{
        width: "100%",
        display: "flex",
        alignItems: "flex-start",
        // ButtonBase centres its content, which would hang the radio circle off
        // the end of the text and put the two options' circles in different
        // places — the shorter description would sit further in than the longer.
        justifyContent: "flex-start",
        gap: 1.5,
        textAlign: "left",
        px: 2,
        py: 1.75,
        border: `1px solid ${selected ? cuni.red : paper["300"]}`,
        borderRadius: 1.5,
        bgcolor: selected ? paper["000"] : paper["050"],
        "&:hover": { borderColor: selected ? cuni.red : paper["400"] },
        "&.Mui-disabled": { opacity: 0.5 },
      }}
    >
      <Box
        aria-hidden
        sx={{
          flex: "none",
          mt: 0.25,
          width: 16,
          height: 16,
          borderRadius: "50%",
          border: selected ? `5px solid ${cuni.red}` : `1px solid ${paper["300"]}`,
          bgcolor: paper["000"],
        }}
      />
      <Box>
        <Box sx={{ fontWeight: 600, fontSize: "0.9375rem", lineHeight: 1.3, color: paper["950"] }}>
          {title}
        </Box>
        <Box sx={{ mt: 0.375, fontSize: "0.84375rem", lineHeight: 1.5, color: paper["700"] }}>
          {description}
        </Box>
      </Box>
    </ButtonBase>
  );
}
