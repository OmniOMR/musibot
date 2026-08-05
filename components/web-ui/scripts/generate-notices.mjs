/**
 * Regenerate THIRD-PARTY-NOTICES.md from what this bundle actually ships.
 *
 *     npm run notices
 *
 * The bundle is a redistribution of every library compiled into it, and most
 * permissive licences — BSD, MIT, the SIL Open Font License — require their
 * notice to travel with it. Nothing does that by itself: Vite strips comments,
 * so a licence header inside a dependency's source does not survive into
 * `dist/`. This is what puts it back.
 *
 * It is generated rather than written by hand because a hand-written list is
 * accurate exactly once. Run it whenever a dependency is added or upgraded; the
 * result is committed, so a diff shows what changed.
 *
 * What is included is the production dependency closure, minus two kinds of
 * package that are demonstrably not in `dist/`:
 *
 * - **optional dependencies** — `gl`, which OpenSheetMusicDisplay uses only to
 *   render headlessly under Node, and its native-build toolchain.
 * - **`@types/*`** — type declarations, erased before anything is emitted.
 *
 * Everything else is listed even where it is arguably build-time only. Over-
 * attributing costs a paragraph; under-attributing breaches a licence.
 */
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OUTPUT = join(ROOT, "THIRD-PARTY-NOTICES.md");

/**
 * Licences that offer a choice. npm records the offer; a redistributor has to
 * make the election, and leaving it unmade is how a dual MIT-or-GPL dependency
 * is later read as putting GPL in the web UI.
 */
const ELECTED = {
  jszip: { spdx: "MIT", note: "Offered as `MIT OR GPL-3.0-or-later`; Musibot elects **MIT**." },
};

const LICENCE_FILE = /^(licen[cs]e|copying)(\.|$)/i;

/**
 * `--long` is load-bearing: without it npm omits `path` from every node, and
 * `path` is how each package's own licence file is found. Drop it and the file
 * still generates, still lists every package, and contains not one line of
 * licence text — which is worse than not having it, because it looks done.
 */
function tree() {
  const json = execFileSync("npm", ["ls", "--omit=dev", "--all", "--long", "--json"], {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(json);
}

/**
 * What a package declares as optional.
 *
 * Read from each manifest rather than passing `--omit=optional` to npm, which
 * reports the tree as *installed* — an optional dependency already on disk is
 * still listed, and the whole native-build toolchain under it with it.
 */
function optionalNamesOf(packagePath) {
  try {
    const manifest = JSON.parse(readFileSync(join(packagePath, "package.json"), "utf8"));
    return new Set(Object.keys(manifest.optionalDependencies ?? {}));
  } catch {
    return new Set();
  }
}

function collect(node, into = new Map()) {
  const optional = optionalNamesOf(node.path ?? ROOT);
  for (const [name, dependency] of Object.entries(node.dependencies ?? {})) {
    if (dependency.version === undefined || name.startsWith("@types/") || optional.has(name)) {
      continue;
    }
    const key = `${name}@${dependency.version}`;
    if (!into.has(key)) {
      into.set(key, { name, version: dependency.version, path: dependency.path });
      collect(dependency, into);
    }
  }
  return into;
}

/** The licence text as the package ships it, or null if it ships none. */
function licenceText(packagePath) {
  if (packagePath === undefined) {
    return null;
  }
  try {
    const file = readdirSync(packagePath).find((name) => LICENCE_FILE.test(name));
    return file === undefined ? null : readFileSync(join(packagePath, file), "utf8").trim();
  } catch {
    return null;
  }
}

function declaredLicence(packagePath) {
  try {
    const manifest = JSON.parse(readFileSync(join(packagePath, "package.json"), "utf8"));
    if (typeof manifest.license === "string") {
      return manifest.license;
    }
    if (Array.isArray(manifest.licenses)) {
      return manifest.licenses.map((entry) => entry.type).join(" OR ");
    }
  } catch {
    // Falls through to "not declared", which the output states plainly rather
    // than guessing at.
  }
  return null;
}

const packages = [...collect(tree()).values()].sort((a, b) => a.name.localeCompare(b.name));

const lines = [
  "# Third-party notices",
  "",
  "The Musibot Web UI is distributed as a single JavaScript bundle and a set of font files, and both carry code and data from the projects below. This file is their copyright notices and licence terms, which those licences require to accompany a redistribution.",
  "",
  "Musibot itself is licensed under Apache-2.0; see [LICENSE](../../LICENSE). Nothing here changes that, and nothing here is a licence granted by Musibot.",
  "",
  "**This file is generated.** Run `npm run notices` after adding or upgrading a dependency rather than editing it — a hand-maintained list is accurate exactly once.",
  "",
  "Two entries are worth reading before the list.",
  "",
  "**JSZip** is offered under a choice of licences and Musibot elects MIT, stated below on its own entry. An unstated election is how a dual MIT-or-GPL dependency comes to be read as putting GPL into a web UI.",
  "",
  "**Source Serif 4 and Source Sans 3** are bundled as font files rather than fetched from a CDN — see the component README on why — so the SIL Open Font License travels with them rather than staying on somebody else's server. Both `@fontsource-variable/*` packages declare OFL-1.1 and ship its text, reproduced below.",
  "",
  `Generated from ${packages.length} packages in the production dependency tree, excluding optional dependencies and type-only packages, neither of which reaches the bundle.`,
  "",
  "",
  "## Packages",
  "",
  ...packages.flatMap(({ name, version, path }) => {
    const declared = declaredLicence(path) ?? "not declared in package.json";
    const elected = ELECTED[name];
    const text = licenceText(path);
    return [
      `### ${name} ${version}`,
      "",
      `License: ${declared}`,
      ...(elected === undefined ? [] : ["", elected.note]),
      "",
      text === null
        ? "_This package ships no licence file. See its `package.json` and repository for terms._"
        : ["```", text, "```"].join("\n"),
      "",
      "",
    ];
  }),
];

writeFileSync(OUTPUT, lines.join("\n").replace(/\n{4,}/g, "\n\n\n") + "\n");
console.log(`Wrote ${OUTPUT} — ${packages.length} packages.`);
