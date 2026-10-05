import { describe, expect, it } from "vitest";

import type { Box, CocoLayer } from "./coco";
import {
  boxesToDraw,
  classesIn,
  classOf,
  shownByDefault,
  solo,
  styleOf,
  UNNAMED,
} from "./layoutClasses";
import { overlay } from "../theme";

function box(label: string | null, width = 10, height = 10, id = 0): Box {
  return { id, x: 0, y: 0, width, height, label };
}

function layer(...boxes: Box[]): CocoLayer {
  return { boxes, imageWidth: null, imageHeight: null };
}

describe("the style of a class", () => {
  it("is a colour per family, with the family's measures dashed", () => {
    expect(styleOf("staff")).toEqual({ colour: overlay.red, dashed: false });
    expect(styleOf("staffMeasure")).toEqual({ colour: overlay.red, dashed: true });
    expect(styleOf("grandstaff")).toEqual({ colour: overlay.yellow, dashed: false });
    expect(styleOf("grandstaffMeasure")).toEqual({ colour: overlay.yellow, dashed: true });
    expect(styleOf("system")).toEqual({ colour: overlay.blue, dashed: false });
    expect(styleOf("systemMeasure")).toEqual({ colour: overlay.blue, dashed: true });
  });

  it("is green for the empty staff and for anything the specification does not name", () => {
    expect(styleOf("emptyStaff")).toEqual({ colour: overlay.green, dashed: false });
    expect(styleOf("lyrics")).toEqual({ colour: overlay.green, dashed: false });
  });
});

describe("which classes show before anyone chooses", () => {
  it("is every class but the measures", () => {
    expect(shownByDefault("staff")).toBe(true);
    expect(shownByDefault("emptyStaff")).toBe(true);
    expect(shownByDefault("staffMeasure")).toBe(false);
    expect(shownByDefault("systemMeasure")).toBe(false);
  });

  it("includes a class nobody has heard of, since nothing else would show it", () => {
    expect(shownByDefault("lyrics")).toBe(true);
  });
});

describe("the classes in a layout", () => {
  it("are counted, the specification's first and in its order, the rest alphabetically", () => {
    const counted = classesIn([
      layer(box("staffMeasure"), box("staff"), box("zebra"), box("staff"), box("alpha")),
      layer(box("system"), box("staff")),
    ]);

    expect(counted).toEqual([
      { name: "system", count: 1 },
      { name: "staff", count: 3 },
      { name: "staffMeasure", count: 1 },
      { name: "alpha", count: 1 },
      { name: "zebra", count: 1 },
    ]);
  });

  it("include boxes whose category has no name, under a name of their own", () => {
    expect(classesIn([layer(box(null))])).toEqual([{ name: UNNAMED, count: 1 }]);
  });
});

describe("the boxes drawn", () => {
  it("leave out hidden classes", () => {
    const drawn = boxesToDraw(
      layer(box("staff", 10, 10, 1), box("system", 100, 50, 2), box("staffMeasure", 5, 5, 3)),
      new Set(["staffMeasure"]),
    );

    expect(drawn.map(classOf)).toEqual(["system", "staff"]);
  });

  it("are drawn by class, bottom first, whatever their size", () => {
    // Sizes deliberately at odds with the order, which is the class's alone.
    const classes = [
      "staffMeasure",
      "grandstaffMeasure",
      "systemMeasure",
      "emptyStaff",
      "staff",
      "grandstaff",
      "system",
    ];
    const drawn = boxesToDraw(
      layer(...classes.map((name, index) => box(name, 100 - index, 100 - index, index))),
      new Set(),
    );

    expect(drawn.map(classOf)).toEqual([...classes].reverse());
  });

  it("put a class nobody knows above the empty staff and below the measures", () => {
    const drawn = boxesToDraw(
      layer(box("staffMeasure"), box("lyrics"), box("emptyStaff"), box("system")),
      new Set(),
    );

    expect(drawn.map(classOf)).toEqual(["system", "emptyStaff", "lyrics", "staffMeasure"]);
  });

  it("put the larger box of one class underneath", () => {
    const drawn = boxesToDraw(layer(box("staff", 10, 10, 1), box("staff", 50, 50, 2)), new Set());

    expect(drawn.map((b) => b.id)).toEqual([2, 1]);
  });
});

describe("soloing a class", () => {
  const all = ["system", "staff", "staffMeasure"];

  it("hides every other class", () => {
    expect(solo("staff", all, new Set())).toEqual(new Set(["system", "staffMeasure"]));
  });

  it("solos it even when it was hidden itself", () => {
    expect(solo("staffMeasure", all, new Set(["staffMeasure"]))).toEqual(
      new Set(["system", "staff"]),
    );
  });

  it("shows everything again when it is already the only class showing", () => {
    expect(solo("staff", all, new Set(["system", "staffMeasure"]))).toEqual(new Set());
  });
});
