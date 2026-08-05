import { describe, expect, it } from "vitest";

import { readCoco } from "./coco";

describe("readCoco", () => {
  it("reads boxes and resolves their category names", () => {
    const layer = readCoco({
      images: [{ width: 2325, height: 120 }],
      categories: [{ id: 16, name: "noteheadBlack" }],
      annotations: [{ id: 1, bbox: [426, 0, 58, 120], category_id: 16 }],
    });

    expect(layer.boxes).toEqual([
      { id: 1, x: 426, y: 0, width: 58, height: 120, label: "noteheadBlack" },
    ]);
    expect(layer.imageWidth).toBe(2325);
    expect(layer.imageHeight).toBe(120);
  });

  it("ignores segmentation in both of the shapes it comes in", () => {
    // Polygon arrays in layout.json, run-length encoding in the page
    // detections. Drawing either would mean an RLE decoder for shapes the
    // boxes already locate — and polygons are the one thing that makes an SVG
    // scene slow, where rectangles do not.
    const layer = readCoco({
      annotations: [
        { id: 1, bbox: [0, 0, 10, 10], segmentation: [[1, 2, 3, 4]] },
        { id: 2, bbox: [5, 5, 10, 10], segmentation: { size: [26, 21], counts: [16, 7] } },
      ],
    });

    expect(layer.boxes).toHaveLength(2);
    expect(layer.boxes[0]).not.toHaveProperty("segmentation");
  });

  it("leaves a box unlabelled when the file names no categories", () => {
    const layer = readCoco({ annotations: [{ id: 1, bbox: [0, 0, 1, 1], category_id: 3 }] });

    expect(layer.boxes[0].label).toBeNull();
  });

  it("skips an annotation with no usable box rather than refusing the file", () => {
    // Musibot never parses a File — it only moves them around — so nothing has
    // checked this before it arrives. One bad annotation is not a reason the
    // page will not render.
    const layer = readCoco({
      annotations: [
        { id: 1, bbox: [0, 0, 10, 10] },
        { id: 2 },
        { id: 3, bbox: [1, 2] },
        { id: 4, bbox: ["a", "b", "c", "d"] },
      ],
    });

    expect(layer.boxes.map((box) => box.id)).toEqual([1]);
  });

  it("has nothing to draw for something that is not a COCO file at all", () => {
    expect(readCoco(null).boxes).toEqual([]);
    expect(readCoco("<?xml version='1.0'?>").boxes).toEqual([]);
    expect(readCoco({}).boxes).toEqual([]);
  });
});
