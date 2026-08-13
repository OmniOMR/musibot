import { openStream } from "./stream";
import type { ExecutionResultView } from "./types";

/**
 * Every *Pipeline Execution* of this token's identity that ends, as it ends.
 *
 * The one stream scoped to a *User* rather than a page — which is why it takes
 * no page ID and why a caller watching one page filters on `page_id`. Musibot
 * has no sessions, so it carries every page of the identity, including pages
 * another holder of the same *Library* token created; this app only ever cares
 * about the ones in its own ledger.
 *
 * Nothing is replayed, so a caller **reconciles on connect**: an execution that
 * ended while the connection was down is not announced afterwards, and the way
 * to learn about it is to ask.
 */
export function openExecutionResults(
  token: string,
  signal?: AbortSignal,
): Promise<AsyncGenerator<ExecutionResultView>> {
  return openStream<ExecutionResultView>("/pipeline-execution-results", token, signal);
}
