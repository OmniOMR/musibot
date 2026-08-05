import { createTheme } from "@mui/material/styles";

import { cuni, paper } from "./palette";

/**
 * The Musibot MUI theme.
 *
 * The look is printed paper: a warm ivory page, a serif for headings, flat
 * surfaces separated by hairline rules instead of drop shadows, and Charles
 * University's cardinal red as the one saturated colour on the page.
 *
 * Light only, deliberately. The paper metaphor does not survive inversion —
 * a dark rendering of this design is not this design in the dark, it is a
 * different design — so rather than ship a second theme that nobody checks,
 * there is one. See `README.md`.
 */

const SERIF = '"Source Serif 4 Variable", Georgia, "Times New Roman", serif';
const SANS = '"Source Sans 3 Variable", system-ui, -apple-system, "Segoe UI", sans-serif';

/**
 * The monospace stack, exported because the design reaches for it far outside
 * `<code>`: file paths, page IDs, pipeline versions, log lines, image
 * dimensions — anything the user might have to read character by character or
 * type back. Setting it on a MUI component means naming it, since the class
 * that component generates outranks the element rule in `CssBaseline`.
 */
export const mono = 'ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace';

export const theme = createTheme({
  cssVariables: true,

  palette: {
    mode: "light",

    primary: {
      main: cuni.red,
      // Both hover and any red that carries text land on the manual's darker
      // red — `cuni.red` itself is only 4.75:1 on the page (see palette.ts).
      dark: cuni.redDark,
      light: "#e05c6c",
      contrastText: paper["000"],
    },

    secondary: {
      main: cuni.blue,
      dark: "#002740",
      light: "#1c5578",
      contrastText: paper["000"],
    },

    // MUI's stock `grey` is cool-toned, and it reaches far further into the
    // component styles than it first appears — dividers, disabled states,
    // outlined-input borders, Skeleton, the lot. Left alone, every one of
    // those renders blue-grey against an ivory page and the paper illusion
    // collapses. So it is replaced outright, step for step.
    grey: {
      50: paper["050"],
      100: paper["100"],
      200: paper["200"],
      300: paper["300"],
      400: paper["400"],
      500: paper["500"],
      600: paper["600"],
      700: paper["700"],
      800: paper["800"],
      900: paper["900"],
      A100: paper["150"],
      A200: paper["300"],
      A400: paper["500"],
      A700: paper["700"],
    },

    background: {
      default: paper["050"],
      paper: paper["000"],
    },

    text: {
      primary: paper["900"],
      secondary: paper["700"],
      disabled: paper["400"],
    },

    divider: paper["200"],
  },

  // prettier-ignore — the heading scale is a table and reads as one. Prettier
  // would explode each variant into seven lines and the progression through
  // the scale would stop being visible at a glance.
  // prettier-ignore
  typography: {
    fontFamily: SANS,
    fontSize: 16,

    // Headings are the serif. Weights stay moderate — Source Serif at 700 on
    // a warm background is heavier than the design wants; 600 reads as
    // "printed" where 700 reads as "shouted".
    h1: { fontFamily: SERIF, fontWeight: 600, fontSize: "3rem", lineHeight: 1.15, letterSpacing: "-0.02em" },
    h2: { fontFamily: SERIF, fontWeight: 600, fontSize: "2.25rem", lineHeight: 1.2, letterSpacing: "-0.015em" },
    h3: { fontFamily: SERIF, fontWeight: 600, fontSize: "1.75rem", lineHeight: 1.25, letterSpacing: "-0.01em" },
    h4: { fontFamily: SERIF, fontWeight: 600, fontSize: "1.4rem", lineHeight: 1.3 },
    h5: { fontFamily: SERIF, fontWeight: 600, fontSize: "1.2rem", lineHeight: 1.35 },
    h6: { fontFamily: SERIF, fontWeight: 600, fontSize: "1.05rem", lineHeight: 1.4 },

    body1: { fontSize: "1rem", lineHeight: 1.65 },
    body2: { fontSize: "0.9375rem", lineHeight: 1.6 },

    // Buttons and labels stay in the sans and stop shouting: MUI uppercases
    // button text by default, which fights a book-like page.
    button: { textTransform: "none", fontWeight: 600, letterSpacing: 0 },
    caption: { fontSize: "0.8125rem", lineHeight: 1.5 },
    overline: { fontWeight: 600, letterSpacing: "0.08em" },
  },

  shape: {
    borderRadius: 6,
  },

  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // A serif at heading sizes on a warm background is the case where
        // these actually show; the fonts themselves are weight-only variable
        // builds, so there is no optical-sizing axis to ask for (see
        // main.tsx).
        html: {
          WebkitFontSmoothing: "antialiased",
          MozOsxFontSmoothing: "grayscale",
          textRendering: "optimizeLegibility",
        },
        // Line lengths, borrowed as an idea from claude.com, which tokenises
        // the same thing. Long measure is the most common way a clean type
        // scale still ends up unreadable.
        ":root": {
          "--measure-narrow": "20ch",
          "--measure-headline": "30ch",
          "--measure-body": "65ch",
          "--measure-prose": "80ch",
        },
        code: { fontFamily: mono, fontSize: "0.9em" },
        pre: { fontFamily: mono },
      },
    },

    // Paper does not cast shadows. Surfaces are separated from the page by a
    // hairline rule and a half-step of tone, which is what a card on a desk
    // actually looks like.
    MuiPaper: {
      defaultProps: {
        elevation: 0,
      },
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
        outlined: {
          borderColor: paper["200"],
        },
      },
    },

    MuiAppBar: {
      defaultProps: {
        elevation: 0,
        color: "transparent",
      },
      styleOverrides: {
        root: {
          backgroundColor: paper["050"],
          borderBottom: `1px solid ${paper["200"]}`,
        },
      },
    },

    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: {
          paddingInline: "1.1em",
        },
        outlined: {
          borderColor: paper["300"],
        },
      },
    },

    MuiLink: {
      defaultProps: {
        underline: "hover",
      },
      styleOverrides: {
        root: {
          // Text red, not fill red — see palette.ts.
          color: cuni.redDark,
          textUnderlineOffset: "0.2em",
        },
      },
    },

    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: paper["200"],
        },
      },
    },

    MuiOutlinedInput: {
      styleOverrides: {
        notchedOutline: {
          borderColor: paper["300"],
        },
      },
    },

    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: paper["900"],
          fontSize: "0.8125rem",
        },
      },
    },
  },
});

export default theme;
