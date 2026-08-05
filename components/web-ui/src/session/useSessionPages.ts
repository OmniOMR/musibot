import { useEffect, useState } from "react";

import { getPage } from "../api/client";
import { ApiError } from "../api/errors";
import type { PipelineExecutionView } from "../api/types";
import type { TrackedPage } from "./ledger";
import { useSession } from "./useSession";

/**
 * The session's pages, each with what the server currently says about it.
 *
 * The ledger knows what was uploaded and when it expires; it does not know how
 * the reading went, because that changes on the server after the upload is
 * over. So each page is asked once when the list opens.
 *
 * One request per page, and each with **that page's own token** — a visitor
 * who has been here an hour holds several sessions, and asking about last
 * hour's page with this hour's token answers `404`. See `ledger.ts`.
 *
 * Asked once rather than polled. This is a list somebody glances at on the way
 * back to a page, not a screen they watch a recognition finish on — that is
 * what the page's own screen is for, and it polls.
 */
export interface SessionPageView {
  page: TrackedPage;
  /** When it will be deleted, which is when its session expires. */
  expiresAt: Date | null;
  /**
   * What the row says under the filename, including while the answer is still
   * on its way — there is no separate loading flag, because a row that said
   * nothing would just be a row that looked broken for a moment.
   */
  status: string;
  tone: "normal" | "error" | "muted";
}

export function useSessionPages(): SessionPageView[] {
  const session = useSession();
  const [statuses, setStatuses] = useState<
    Map<string, { status: string; tone: SessionPageView["tone"] }>
  >(new Map());

  // The page IDs as one string, so the effect runs when the set changes rather
  // than on every render the ledger produces a new array on.
  const identity = session.pages.map((page) => page.pageId).join("|");

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const answers = await Promise.all(
        session.pages.map(async (page) => {
          try {
            const view = await getPage(page.token, page.pageId);
            return [page.pageId, describe(view.executions, page)] as const;
          } catch (error) {
            if (error instanceof ApiError && error.status === 404) {
              // Deleted, or the service restarted and lost it. Either way it
              // is not there, and saying so beats an eternal "checking".
              return [page.pageId, { status: "no longer on the server", tone: "muted" }] as const;
            }
            return [page.pageId, { status: "could not be checked", tone: "muted" }] as const;
          }
        }),
      );

      if (!cancelled) {
        setStatuses(new Map(answers));
      }
    })();

    return () => {
      cancelled = true;
    };
    // `identity` stands for the set of pages; `session.pages` is a fresh array
    // on every render and would re-fetch forever.
  }, [identity]);

  return session.pages.map((page) => {
    const answer = statuses.get(page.pageId);
    return {
      page,
      expiresAt: session.expiryOf(page.pageId),
      status: answer?.status ?? "checking…",
      tone: answer?.tone ?? "muted",
    };
  });
}

/**
 * What the row says, from the executions the page has had.
 *
 * The last execution is the one that speaks for the page: a second run is
 * usually a correction of the first, and a row has space for one line.
 */
function describe(
  executions: PipelineExecutionView[],
  page: TrackedPage,
): { status: string; tone: SessionPageView["tone"] } {
  const last = executions.at(-1);
  if (last === undefined) {
    // Recorded before anything was started on it, which the upload flow does
    // not produce but a page created by hand would.
    const named =
      page.pipelineName === null ? "" : `${page.pipelineName} v${page.pipelineVersion} · `;
    return { status: `${named}nothing run yet`, tone: "muted" };
  }

  const pipeline = `${last.pipeline_name} v${last.pipeline_version}`;
  switch (last.state) {
    case "queued":
      return { status: `${pipeline} · waiting for a worker`, tone: "normal" };
    case "running":
      return { status: `${pipeline} · reading`, tone: "normal" };
    case "completed":
      return { status: `${pipeline} · read`, tone: "normal" };
    case "failed":
      return {
        status: `${pipeline} · failed${last.error === null ? "" : ` — ${last.error}`}`,
        tone: "error",
      };
    default:
      return { status: `${pipeline} · ${last.state}`, tone: "normal" };
  }
}
