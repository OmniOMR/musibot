import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import SessionPill from "./SessionPill";
import SessionProvider from "../session/SessionProvider";

function inAnHour(): string {
  return new Date(Date.now() + 60 * 60_000).toISOString();
}

function seed(pageIds: string[]): void {
  localStorage.setItem(
    "musibot.ledger.v1",
    JSON.stringify({
      sessions: [{ token: "t", expiresAt: inAnHour() }],
      pages: pageIds.map((pageId) => ({
        pageId,
        token: "t",
        fileName: `${pageId}.jpg`,
        createdAt: new Date().toISOString(),
        pipelineName: null,
        pipelineVersion: null,
      })),
    }),
  );
}

function renderPill() {
  return render(
    <SessionProvider>
      <MemoryRouter>
        <SessionPill />
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe("SessionPill", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("says nothing at all on a first visit", () => {
    // Absent rather than empty: a landing page nobody has used yet should not
    // raise the idea of a session only to report that there isn't one.
    renderPill();

    expect(screen.queryByRole("link")).toBeNull();
  });

  it("counts the pages, and counts one in the singular", () => {
    seed(["aaa"]);
    renderPill();

    expect(screen.getByRole("link")).toHaveTextContent("1 page this session");
  });

  it("links to the session overview", () => {
    seed(["aaa", "bbb", "ccc"]);
    renderPill();

    const link = screen.getByRole("link");
    expect(link).toHaveTextContent("3 pages this session");
    expect(link).toHaveAttribute("href", "/session");
  });
});
