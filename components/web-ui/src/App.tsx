import { createBrowserRouter, RouterProvider } from "react-router";

import { routes } from "./routes";
import SessionProvider from "./session/SessionProvider";

/**
 * The app: a router over the screens in `routes.tsx`, and nothing else yet.
 *
 * `basename` is the load-bearing line. Musibot is published under a path
 * prefix — `https://<host>/musibot/` — and this is what lets every route in
 * `paths.ts` be written as if the app sat at the root of a host. Vite hands
 * the prefix over as `import.meta.env.BASE_URL` (always with a trailing slash,
 * which react-router handles), and the dev server serves under the same one,
 * so there is no branch between development and production. Drop it and every
 * link works locally and misses the deployment.
 *
 * A deep link survives a reload because nginx answers any path under the base
 * with `index.html` — `try_files` in `deploy/nginx/musibot.conf.template` —
 * and the router then reads the address bar. Without that the server would
 * answer 404 to everything but the landing page, which is the usual way an
 * SPA's routing is found to be broken.
 */
const router = createBrowserRouter(routes, {
  basename: import.meta.env.BASE_URL,
});

export default function App() {
  return (
    <SessionProvider>
      <RouterProvider router={router} />
    </SessionProvider>
  );
}
