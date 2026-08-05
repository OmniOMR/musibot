import { describe, expect, it } from "vitest";

import type { FileView } from "../api/types";
import type { FileRow } from "../page/files";
import { cuni } from "../theme";
import { instanceLabel, pathsOf, sceneFor } from "./scene";

function file(path: string): FileView {
  return { path, size: 100, last_modified: "2026-08-05T12:00:00Z" };
}

function row(label: string, paths: string[]): FileRow {
  return {
    key: label,
    label,
    prefix: "",
    name: label,
    paths,
    size: 100,
    instances: paths.length > 1 ? paths.length : null,
    isSource: false,
    willBeOverwritten: false,
  };
}

const PAGE = [file("image.jpg"), file("layout.json"), file("coco-object-detection.json")];

const STAVES = [
  file("Staves/1/image.jpg"),
  file("Staves/2/image.jpg"),
  file("Staves/10/image.jpg"),
  file("Staves/1/coco-object-detection.json"),
  file("Staves/2/coco-object-detection.json"),
  file("Staves/10/coco-object-detection.json"),
];

describe("sceneFor", () => {
  it("shows the page image on its own when the image is selected", () => {
    const scene = sceneFor(row("image.jpg", ["image.jpg"]), PAGE, new Map());

    expect(scene.plates.map((plate) => plate.path)).toEqual(["image.jpg"]);
    expect(scene.overlayColour).toBeNull();
  });

  it("puts a boxes layer over the image it is about", () => {
    // layout.json is a set of coordinates and means nothing floating in space,
    // so selecting it shows the page image with the boxes over it.
    const scene = sceneFor(row("layout.json", ["layout.json"]), PAGE, new Map());

    expect(scene.plates).toHaveLength(1);
    expect(scene.plates[0].path).toBe("image.jpg");
    expect(scene.plates[0].overlayPath).toBe("layout.json");
  });

  it("colours staff regions red and symbol detections blue", () => {
    expect(sceneFor(row("layout.json", ["layout.json"]), PAGE, new Map()).overlayColour).toBe(
      cuni.red,
    );
    expect(
      sceneFor(row("coco-object-detection.json", ["coco-object-detection.json"]), PAGE, new Map())
        .overlayColour,
    ).toBe(cuni.blue);
  });

  it("gives a transcription no boxes at all", () => {
    // There is no coordinate in a MusicXML file; it is not aligned to the image.
    const files = [...PAGE, file("transcription.musicxml")];
    const scene = sceneFor(
      row("transcription.musicxml", ["transcription.musicxml"]),
      files,
      new Map(),
    );

    expect(scene.overlayColour).toBeNull();
    expect(scene.plates[0].overlayPath).toBeNull();
  });

  it("shows every staff at once, never one on its own", () => {
    // The design is firm about this: what a reader is checking is whether the
    // reading is right across the page, and isolating staff 4 hides that.
    const scene = sceneFor(row("Staves/{s}/image.jpg", ["Staves/1/image.jpg"]), STAVES, new Map());

    expect(scene.plates).toHaveLength(3);
  });

  it("orders staves numerically, so 10 comes after 2", () => {
    const scene = sceneFor(row("Staves/{s}/image.jpg", ["Staves/1/image.jpg"]), STAVES, new Map());

    expect(scene.plates.map((plate) => plate.instance)).toEqual(["1", "2", "10"]);
  });

  it("stacks the crops using their measured heights", () => {
    const heights = new Map([
      ["Staves/1/image.jpg", 100],
      ["Staves/2/image.jpg", 200],
      ["Staves/10/image.jpg", 50],
    ]);
    const scene = sceneFor(row("Staves/{s}/image.jpg", ["Staves/1/image.jpg"]), STAVES, heights);

    // Each plate starts below the previous one plus the gap.
    expect(scene.plates.map((plate) => plate.y)).toEqual([0, 160, 420]);
  });

  it("gives each staff the overlay that belongs to it", () => {
    const selection = row("Staves/{s}/coco-object-detection.json", [
      "Staves/1/coco-object-detection.json",
      "Staves/2/coco-object-detection.json",
      "Staves/10/coco-object-detection.json",
    ]);
    const scene = sceneFor(selection, STAVES, new Map());

    expect(scene.plates.map((plate) => plate.overlayPath)).toEqual([
      "Staves/1/coco-object-detection.json",
      "Staves/2/coco-object-detection.json",
      "Staves/10/coco-object-detection.json",
    ]);
  });

  it("says so when there is no image to show a layer over", () => {
    // A staff-level run leaves a page with no page-level image at all.
    const scene = sceneFor(row("layout.json", ["layout.json"]), [file("layout.json")], new Map());

    expect(scene.plates).toEqual([]);
    expect(scene.empty).not.toBeNull();
  });

  it("asks for the images and the overlays together", () => {
    const selection = row("Staves/{s}/coco-object-detection.json", [
      "Staves/1/coco-object-detection.json",
      "Staves/2/coco-object-detection.json",
      "Staves/10/coco-object-detection.json",
    ]);

    expect(pathsOf(sceneFor(selection, STAVES, new Map()))).toEqual([
      "Staves/1/image.jpg",
      "Staves/1/coco-object-detection.json",
      "Staves/2/image.jpg",
      "Staves/2/coco-object-detection.json",
      "Staves/10/image.jpg",
      "Staves/10/coco-object-detection.json",
    ]);
  });
});

describe("instanceLabel", () => {
  it("names the three subdivisions the specification defines", () => {
    expect(instanceLabel("Staves/7/image.jpg")).toBe("staff 7");
    expect(instanceLabel("Systems/2/image.jpg")).toBe("system 2");
    expect(instanceLabel("Grandstaves/1/image.jpg")).toBe("grandstaff 1");
  });

  it("falls back to the folder's own name for one it does not know", () => {
    expect(instanceLabel("Measures/4/image.jpg")).toBe("Measures 4");
  });

  it("has nothing to say about a page-level file", () => {
    expect(instanceLabel("image.jpg")).toBeNull();
  });
});
