import type { RouteObject } from "react-router";

import LandingScreen from "./screens/LandingScreen";
import MusicorpusPageScreen from "./screens/MusicorpusPageScreen";
import NotFoundScreen from "./screens/NotFoundScreen";
import SessionScreen from "./screens/SessionScreen";
import * as paths from "./paths";

/**
 * Every screen the app has.
 *
 * Kept separate from the router that mounts it (`App.tsx`) so that a test can
 * mount the same table in a memory router — the routing is then checked
 * without a browser history, and the browser-only part left to check is the
 * `basename`.
 *
 * There is deliberately no shared layout route yet. The three screens do not
 * agree on a header: the landing page carries a wordmark and outbound links,
 * the MusicorpusPage screen carries the page's ID, its expiry and its actions,
 * and the session overview is a card with neither. A layout route will earn
 * its place once something genuinely spans them — the session state, most
 * likely — rather than being introduced now for the shape of it.
 */
export const routes: RouteObject[] = [
  {
    path: paths.LANDING,
    Component: LandingScreen,
  },
  {
    // The screen behind an upload. Its `pageId` is the API's 12-character
    // NanoID, so the URL is unguessable and can be pasted to reopen the page
    // for as long as the session behind it lives.
    path: paths.MUSICORPUS_PAGE,
    Component: MusicorpusPageScreen,
  },
  {
    path: paths.SESSION,
    Component: SessionScreen,
  },
  {
    // nginx serves index.html for any path under the base (`try_files` in
    // deploy/nginx/musibot.conf.template), so a mistyped URL arrives here as a
    // rendered app rather than as a server 404. This is what answers it.
    path: "*",
    Component: NotFoundScreen,
  },
];
