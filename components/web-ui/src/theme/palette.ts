/**
 * The colour tokens the theme is built from.
 *
 * Two sources, and it is worth knowing which is which. The reds and the blue
 * are Charles University's, taken from the official graphics manual and not
 * ours to adjust. The neutral ramp is our own — a single warm hue, generated
 * as an even ladder so that every step is a deliberate distance from its
 * neighbours rather than a colour somebody once picked in a picker.
 */

/**
 * Charles University's institutional colours.
 *
 * From the UK graphics manual (`UK-13122-version1-or___45_2023_priloha.pdf`),
 * the "Použité barvy propagačního logotypu UK" page. Musibot is built at the
 * university, so the primary is theirs rather than an invention of ours.
 *
 * A caveat for whoever checks these against the PDF: it states the red twice
 * and the two do not agree — `#d22d40` on the palette page, `#d32e3f` in the
 * later application examples. We take the palette page as authoritative.
 */
export const cuni = {
  /** Cardinal red, from the historic university coat of arms. Pantone 193 C. */
  red: "#d22d40",
  /** The manual's own darker red. We use it wherever red must carry text. */
  redDark: "#ae2f3c",
  /** The official secondary. Pantone 302 C. */
  blue: "#003657",
} as const;

/**
 * The warm neutral ramp.
 *
 * This is the part that makes the paper look work, and the part that is easy
 * to get wrong. It is not a beige background over neutral grey furniture —
 * *everything* neutral is warm, including borders, dividers, disabled
 * controls and placeholder text. A single cool grey among them reads as a
 * stain, because the eye judges these colours against each other and not
 * against white.
 *
 * Which is why MUI's default `grey` palette has to be overridden wholesale
 * rather than supplemented; see `theme.ts`.
 *
 * Generated at hue 44° with saturation high at the light end — that is the
 * only place warmth is visible at all — tapering toward the dark end, where
 * more of it would read as brown rather than as ink.
 */
export const paper = {
  "000": "#ffffff",
  "050": "#faf9f4", // the page itself
  "100": "#f7f4ee", // a surface raised off the page
  "150": "#f0ede5", // hover on that surface
  "200": "#e7e4d9", // borders and dividers
  "300": "#d6d1c2", // a stronger border, disabled outline
  "400": "#bab3a0", // disabled text, placeholder
  "500": "#9c947c",
  "600": "#756e5c", // muted text (4.81:1 on the page — AA)
  "700": "#585346", // secondary text (7.27:1 — AAA)
  "800": "#3e3b32",
  "900": "#272520", // body text (14.52:1)
  "950": "#161512", // headings
} as const;

/**
 * Contrast ratios against `paper.050`, measured rather than assumed. Kept
 * here so a future change to the ramp can be checked against the same
 * numbers instead of being re-derived from scratch.
 *
 *   paper.900 on page   14.52   body text          AAA
 *   paper.700 on page    7.27   secondary text     AAA
 *   paper.600 on page    4.81   muted text         AA
 *   cuni.redDark on page 6.09   links, red text    AA
 *   cuni.red on page     4.75   red on the page    AA (no headroom — see below)
 *   white on cuni.red    5.01   filled red button  AA
 *   white on redDark     6.42   its hover state    AA
 *   cuni.blue on page   11.96   blue text          AAA
 *
 * `cuni.red` clears AA for normal text by 0.25, which is not enough headroom
 * to spend on small or light-weight text. So the rule the theme encodes is:
 * `cuni.red` fills shapes, `cuni.redDark` carries text.
 */
