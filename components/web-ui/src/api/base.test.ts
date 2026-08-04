import { describe, expect, it } from "vitest";

import { API_BASE_URL, apiUrl } from "./base";

/**
 * The failure this guards is the quiet kind: an absolute `/api/...` works at
 * the origin root and in every test, and 404s only once the bundle is served
 * under `/musibot/`. Vitest runs with the same `base` as the build, so these
 * assert the deployed shape rather than a hypothetical one.
 */
describe("the API base URL", () => {
  it("sits under the path the bundle is served from", () => {
    expect(API_BASE_URL).toBe(`${import.meta.env.BASE_URL}api`);
    expect(API_BASE_URL.startsWith("/")).toBe(true);
    expect(API_BASE_URL.endsWith("/api")).toBe(true);
  });

  it("joins endpoint paths with exactly one slash", () => {
    expect(apiUrl("/pipelines")).toBe(`${API_BASE_URL}/pipelines`);
    expect(apiUrl("pipelines")).toBe(`${API_BASE_URL}/pipelines`);
  });
});
