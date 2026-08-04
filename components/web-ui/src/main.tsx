import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";

// Fonts are bundled rather than fetched from the Google Fonts CDN. Musibot is
// a university service deployed in the EU, and German courts have found that
// loading fonts from a third-party CDN — which discloses the visitor's IP to
// it — breaches the GDPR. Self-hosting also removes a render-blocking request
// to a host we do not control.
//
// Both are imported weight-only. Source Serif also ships a build carrying the
// optical-sizing axis, which would let headings use the display cut of the
// face and body text the text cut — but it costs 122 kB on the latin subset
// against 50 kB for this one, and the serif is the first thing painted on the
// landing page. The refinement is subtle and the 72 kB is not; revisit it if
// the design ever leans harder on the serif than it does now.
//
// Every language subset is bundled. They are separate files behind
// `unicode-range`, so a visitor downloads only the ones their text actually
// needs — and a library's Cyrillic or Greek catalogue metadata renders in the
// right face instead of dropping to a fallback.
import "@fontsource-variable/source-serif-4";
import "@fontsource-variable/source-sans-3";

import App from "./App";
import { theme } from "./theme";

const container = document.getElementById("root");
if (!container) {
  throw new Error("No #root element — index.html and main.tsx disagree.");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </StrictMode>,
);
