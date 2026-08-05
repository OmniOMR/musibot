import "@testing-library/jest-dom/vitest";

/**
 * Browser APIs jsdom does not implement.
 *
 * These are stubs rather than fakes: nothing under test asserts on them, they
 * exist so that a component using one can be rendered at all. A test that
 * actually needs to observe a resize, decode an image or run a zoom gesture
 * belongs in a real browser, which is where the canvas is exercised.
 */

if (!("ResizeObserver" in globalThis)) {
  // Used by ScenePanel to learn its own size, which jsdom lays out as zero.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!("createImageBitmap" in globalThis)) {
  // jsdom decodes nothing. Answering with a zero-sized bitmap keeps the image
  // measuring path from throwing.
  globalThis.createImageBitmap = () =>
    Promise.resolve({ width: 0, height: 0, close() {} } as ImageBitmap);
}

if (!("URL" in globalThis && typeof URL.createObjectURL === "function")) {
  URL.createObjectURL = () => "blob:stub";
  URL.revokeObjectURL = () => {};
}
