import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { musicorpusPagePath } from "./paths";
import { routes } from "./routes";

/**
 * The routing, checked where it is easy to get wrong: which address reaches
 * which screen, that a page ID arrives as a parameter, and that an address
 * nobody claimed lands on the not-found screen rather than a blank page.
 *
 * A memory router rather than the browser one, so the same table can be
 * mounted without a history — `basename` is `App.tsx`'s business and is
 * covered by the base-path tests instead.
 */
function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe("routes", () => {
  it("serves the landing page at the root", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: "Musibot reads sheet music" })).toBeInTheDocument();
  });

  it("serves the session overview", () => {
    renderAt("/session");
    expect(screen.getByRole("heading", { name: "Pages in this session" })).toBeInTheDocument();
  });

  it("passes a page ID through to the MusicorpusPage screen", () => {
    renderAt(musicorpusPagePath("9f3c2aBcD1eF"));
    expect(screen.getByText("9f3c2aBcD1eF")).toBeInTheDocument();
  });

  it("answers an unclaimed address with the not-found screen", () => {
    renderAt("/no-such-thing");
    expect(screen.getByRole("heading", { name: "There is nothing here" })).toBeInTheDocument();
  });
});
