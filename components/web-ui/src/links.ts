import { apiUrl } from "./api/base";

/**
 * Everywhere the app points outside itself.
 *
 * Gathered here because these are the addresses most likely to be wrong: they
 * name things that live outside this repository and change without anything
 * here failing to build. One file to check rather than a search through the
 * markup.
 */

/**
 * The interactive HTTP API documentation, which the `api` service serves
 * itself. Built through `apiUrl` like any other call to the service, so it
 * follows the deployment's path prefix — see `api/base.ts`.
 */
export const HTTP_API_DOCS = apiUrl("/docs");

/**
 * The python client. Not on PyPI while Musibot is on `0.x`, so this points at
 * the component's own README, which carries the git install line. Repoint it at
 * `https://pypi.org/project/musibot-client/` the day it is published.
 */
export const PYTHON_CLIENT =
  "https://github.com/OmniOMR/musibot/tree/main/components/python-client";

/** The project itself, standing in for an about page until there is one. */
export const PROJECT = "https://github.com/OmniOMR/musibot";

/**
 * Where a library or an archive with a whole collection to read should write.
 * The public tier's allowance is nowhere near enough for that work, so this
 * address is the landing page's answer to them rather than the HTTP API.
 */
export const CONTACT_EMAIL = "musibot@ufal.mff.cuni.cz";
