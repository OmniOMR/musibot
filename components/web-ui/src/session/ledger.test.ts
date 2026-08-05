import { beforeEach, describe, expect, it } from "vitest";

import {
  addPage,
  addSession,
  EMPTY,
  forgetSession,
  type Ledger,
  MINIMUM_PAGE_LIFETIME_MS,
  pageExpiry,
  pagesNewestFirst,
  prune,
  read,
  sessionForNewPage,
  tokenForPage,
  write,
  type TrackedPage,
} from "./ledger";

const NOW = new Date("2026-08-05T12:00:00Z");

function at(offsetMinutes: number): string {
  return new Date(NOW.getTime() + offsetMinutes * 60_000).toISOString();
}

function page(pageId: string, token: string, createdAt = at(0)): TrackedPage {
  return {
    pageId,
    token,
    fileName: `${pageId}.jpg`,
    createdAt,
    pipelineName: null,
    pipelineVersion: null,
  };
}

describe("sessionForNewPage", () => {
  it("mints nothing while the current session has plenty of life", () => {
    const ledger = addSession(EMPTY, { token: "fresh", expiresAt: at(60) });

    expect(sessionForNewPage(ledger, NOW)?.token).toBe("fresh");
  });

  it("refuses a session with too little life to give a page", () => {
    // The whole point: a page created here would live 19 minutes through no
    // choice of anyone's, just because of when the visitor arrived.
    const ledger = addSession(EMPTY, { token: "nearly-done", expiresAt: at(19) });

    expect(sessionForNewPage(ledger, NOW)).toBeNull();
  });

  it("holds the threshold exactly", () => {
    const threshold = new Date(NOW.getTime() + MINIMUM_PAGE_LIFETIME_MS).toISOString();
    const ledger = addSession(EMPTY, { token: "borderline", expiresAt: threshold });

    // Not *more* than the minimum, so it does not qualify.
    expect(sessionForNewPage(ledger, NOW)).toBeNull();
  });

  it("prefers the session that lasts longest", () => {
    const ledger = addSession(addSession(EMPTY, { token: "older", expiresAt: at(30) }), {
      token: "newer",
      expiresAt: at(60),
    });

    expect(sessionForNewPage(ledger, NOW)?.token).toBe("newer");
  });

  it("keeps using an old session while it still has life, rather than the newest", () => {
    // Minting is driven by the clock, not by novelty: an ample session is used
    // even after a newer one exists, so nothing re-mints for its own sake.
    const ledger = addSession(EMPTY, { token: "ample", expiresAt: at(45) });

    expect(sessionForNewPage(ledger, NOW)?.token).toBe("ample");
  });
});

describe("prune", () => {
  it("takes a session's pages with it", () => {
    // A page dies with the token it was created under; nothing else decides it.
    let ledger: Ledger = addSession(EMPTY, { token: "gone", expiresAt: at(-1) });
    ledger = addSession(ledger, { token: "here", expiresAt: at(40) });
    ledger = addPage(ledger, page("aaa", "gone"));
    ledger = addPage(ledger, page("bbb", "here"));

    const pruned = prune(ledger, NOW);

    expect(pruned.sessions.map((session) => session.token)).toEqual(["here"]);
    expect(pruned.pages.map((tracked) => tracked.pageId)).toEqual(["bbb"]);
  });

  it("drops a page whose session is not recorded at all", () => {
    // Without the token there is no way to ask about it, so it is unreachable
    // rather than merely old.
    const ledger = addPage(EMPTY, page("orphan", "a-token-nobody-has"));

    expect(prune(ledger, NOW).pages).toEqual([]);
  });
});

describe("forgetSession", () => {
  it("drops the session and its pages, leaving the others", () => {
    // What a 401 causes: proof the token is dead however much life was
    // recorded for it, since the service rebuilds its state empty on restart.
    let ledger: Ledger = addSession(EMPTY, { token: "dead", expiresAt: at(50) });
    ledger = addSession(ledger, { token: "live", expiresAt: at(50) });
    ledger = addPage(ledger, page("aaa", "dead"));
    ledger = addPage(ledger, page("bbb", "live"));

    const after = forgetSession(ledger, "dead");

    expect(after.sessions.map((session) => session.token)).toEqual(["live"]);
    expect(after.pages.map((tracked) => tracked.pageId)).toEqual(["bbb"]);
  });
});

describe("a page's token", () => {
  it("is the one it was created under, not the current one", () => {
    // The mistake this guards: asking about an old page with the newest token
    // answers 404, because to the service that is somebody else's page.
    let ledger: Ledger = addSession(EMPTY, { token: "first", expiresAt: at(10) });
    ledger = addSession(ledger, { token: "second", expiresAt: at(60) });
    ledger = addPage(ledger, page("old-page", "first"));

    expect(sessionForNewPage(ledger, NOW)?.token).toBe("second");
    expect(tokenForPage(ledger, "old-page")).toBe("first");
  });

  it("fixes when the page expires", () => {
    let ledger: Ledger = addSession(EMPTY, { token: "first", expiresAt: at(10) });
    ledger = addPage(ledger, page("old-page", "first"));

    expect(pageExpiry(ledger, ledger.pages[0])?.toISOString()).toBe(at(10));
  });

  it("is null for a page this browser never created", () => {
    expect(tokenForPage(EMPTY, "somebody-elses")).toBeNull();
  });
});

describe("addPage", () => {
  it("replaces what is known about a page rather than duplicating it", () => {
    let ledger: Ledger = addPage(EMPTY, page("aaa", "token"));
    ledger = addPage(ledger, { ...page("aaa", "token"), pipelineName: "page-to-musicxml" });

    expect(ledger.pages).toHaveLength(1);
    expect(ledger.pages[0].pipelineName).toBe("page-to-musicxml");
  });
});

describe("pagesNewestFirst", () => {
  it("puts the most recent upload at the top", () => {
    let ledger: Ledger = addPage(EMPTY, page("older", "token", at(-30)));
    ledger = addPage(ledger, page("newer", "token", at(-5)));

    expect(pagesNewestFirst(ledger).map((tracked) => tracked.pageId)).toEqual(["newer", "older"]);
  });
});

describe("persistence", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips", () => {
    const ledger = addPage(addSession(EMPTY, { token: "t", expiresAt: at(50) }), page("aaa", "t"));

    write(ledger);

    expect(read()).toEqual(ledger);
  });

  it("reads an empty ledger when nothing was stored", () => {
    expect(read()).toEqual(EMPTY);
  });

  it("discards a stored value it cannot make sense of", () => {
    // localStorage outlives versions of this app and can be edited by hand.
    // Losing the record of an ephemeral hour beats a landing page that throws.
    localStorage.setItem("musibot.ledger.v1", "{not json at all");
    expect(read()).toEqual(EMPTY);

    localStorage.setItem("musibot.ledger.v1", JSON.stringify({ sessions: "nonsense" }));
    expect(read()).toEqual(EMPTY);
  });

  it("keeps the entries that parse and drops the ones that do not", () => {
    localStorage.setItem(
      "musibot.ledger.v1",
      JSON.stringify({
        sessions: [{ token: "t", expiresAt: at(50) }, { token: 42 }],
        pages: [page("aaa", "t"), { pageId: "no-token" }],
      }),
    );

    const ledger = read();

    expect(ledger.sessions).toHaveLength(1);
    expect(ledger.pages).toHaveLength(1);
  });
});
