import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SessionProvider from "./SessionProvider";
import { useSession } from "./useSession";

const mintPublicSession = vi.hoisted(() => vi.fn());
vi.mock("../api/client", () => ({ mintPublicSession }));

function inAnHour(): string {
  return new Date(Date.now() + 60 * 60_000).toISOString();
}

/** Asks for a token as an upload would, and shows what came back. */
function TokenTaker({ times = 1 }: { times?: number }) {
  const { tokenForNewPage } = useSession();

  return (
    <button
      onClick={() => {
        // Fired together on purpose — three files dropped at once must not
        // become three sessions.
        for (let index = 0; index < times; index += 1) {
          void tokenForNewPage();
        }
      }}
    >
      take
    </button>
  );
}

function PageLister() {
  const { pages } = useSession();
  return <output>{pages.map((page) => page.pageId).join(",")}</output>;
}

describe("SessionProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    mintPublicSession.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("mints once when several uploads start at the same moment", async () => {
    // Without the in-flight guard each caller would open its own request and
    // the visitor would collect a session per dropped file — the spamming the
    // whole rule exists to avoid.
    mintPublicSession.mockResolvedValue({ token: "minted", expires_at: inAnHour() });

    render(
      <SessionProvider>
        <TokenTaker times={3} />
      </SessionProvider>,
    );
    screen.getByRole("button").click();

    await waitFor(() => expect(mintPublicSession).toHaveBeenCalledTimes(1));
  });

  it("does not mint again while the stored session has life left", async () => {
    localStorage.setItem(
      "musibot.ledger.v1",
      JSON.stringify({ sessions: [{ token: "stored", expiresAt: inAnHour() }], pages: [] }),
    );

    render(
      <SessionProvider>
        <TokenTaker />
      </SessionProvider>,
    );
    screen.getByRole("button").click();

    await waitFor(() => expect(mintPublicSession).not.toHaveBeenCalled());
  });

  it("mints when the stored session is nearly over", async () => {
    localStorage.setItem(
      "musibot.ledger.v1",
      JSON.stringify({
        sessions: [{ token: "nearly", expiresAt: new Date(Date.now() + 5 * 60_000).toISOString() }],
        pages: [],
      }),
    );
    mintPublicSession.mockResolvedValue({ token: "minted", expires_at: inAnHour() });

    render(
      <SessionProvider>
        <TokenTaker />
      </SessionProvider>,
    );
    screen.getByRole("button").click();

    await waitFor(() => expect(mintPublicSession).toHaveBeenCalledTimes(1));
  });

  it("forgets an expired session's pages when it loads", () => {
    // The ledger outlives the tab; a page whose session ran out overnight is
    // gone from the server and must not be listed as though it were not.
    localStorage.setItem(
      "musibot.ledger.v1",
      JSON.stringify({
        sessions: [
          { token: "gone", expiresAt: new Date(Date.now() - 60_000).toISOString() },
          { token: "here", expiresAt: inAnHour() },
        ],
        pages: [
          {
            pageId: "expired",
            token: "gone",
            fileName: "a.jpg",
            createdAt: "2026-01-01T00:00:00Z",
          },
          { pageId: "alive", token: "here", fileName: "b.jpg", createdAt: "2026-01-01T00:00:00Z" },
        ],
      }),
    );

    render(
      <SessionProvider>
        <PageLister />
      </SessionProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("alive");
    expect(screen.getByRole("status")).not.toHaveTextContent("expired");
  });
});
