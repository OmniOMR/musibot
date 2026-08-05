import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { musicorpusPagePath } from "./paths";
import { routes } from "./routes";
import SessionProvider from "./session/SessionProvider";

/**
 * The routing, checked where it is easy to get wrong: which address reaches
 * which screen, that a page ID arrives as a parameter, and that an address
 * nobody claimed lands on the not-found screen rather than a blank page.
 *
 * A memory router rather than the browser one, so the same table can be
 * mounted without a history — `basename` is `App.tsx`'s business and is
 * covered by the base-path tests instead.
 */
/** A page in the ledger, as an upload would have left one. */
function seedPage(pageId: string): void {
  localStorage.setItem(
    "musibot.ledger.v1",
    JSON.stringify({
      sessions: [{ token: "t", expiresAt: new Date(Date.now() + 60 * 60_000).toISOString() }],
      pages: [
        {
          pageId,
          token: "t",
          fileName: "kyrie-p3.jpg",
          createdAt: new Date().toISOString(),
          pipelineName: null,
          pipelineVersion: null,
        },
      ],
    }),
  );
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  // The same composition as `App.tsx`: screens reach for the session, so a
  // router mounted without the provider around it is not the app.
  return render(
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>,
  );
}

describe("routes", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("serves the landing page at the root", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: "Musibot reads sheet music" })).toBeInTheDocument();
  });

  it("serves the session overview", () => {
    renderAt("/session");
    expect(screen.getByRole("heading", { name: "Pages in this session" })).toBeInTheDocument();
  });

  it("passes a page ID through to the MusicorpusPage screen", () => {
    seedPage("9f3c2aBcD1eF");
    renderAt(musicorpusPagePath("9f3c2aBcD1eF"));

    expect(screen.getByText(/9f3c2aBcD1eF/)).toBeInTheDocument();
  });

  it("says so when a page was not uploaded from this browser", () => {
    // A page is reached with the token it was created under, which lives in one
    // browser's localStorage and is never in the URL. A pasted link is
    // therefore not a way in, and this is the screen that admits it rather than
    // showing an empty workspace.
    renderAt(musicorpusPagePath("somebodyelses"));

    expect(
      screen.getByRole("heading", { name: "This page was not uploaded from this browser" }),
    ).toBeInTheDocument();
  });

  it("answers an unclaimed address with the not-found screen", () => {
    renderAt("/no-such-thing");
    expect(screen.getByRole("heading", { name: "There is nothing here" })).toBeInTheDocument();
  });
});
