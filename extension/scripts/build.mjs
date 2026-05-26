import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const dist = resolve(root, "dist");

const SHARED_ENTRIES = [
  "src/background.js",
  "src/content.js",
  "src/popup.js",
  "src/options.js",
];

const SHARED_STATIC = [
  ["src/popup.html", "popup.html"],
  ["src/options.html", "options.html"],
];

async function buildVariant({ name, manifest, target }) {
  const outdir = resolve(dist, name);
  await rm(outdir, { recursive: true, force: true });
  await mkdir(outdir, { recursive: true });

  await build({
    entryPoints: SHARED_ENTRIES.map((rel) => resolve(root, rel)),
    bundle: true,
    format: "iife",
    target,
    outdir,
    logLevel: "info",
  });

  await cp(resolve(root, manifest), resolve(outdir, "manifest.json"));
  for (const [src, dst] of SHARED_STATIC) {
    await cp(resolve(root, src), resolve(outdir, dst));
  }

  console.log(`Built ${name} extension to ${outdir}`);
}

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

await buildVariant({
  name: "chrome",
  manifest: "manifest.json",
  target: ["chrome114"],
});

await buildVariant({
  name: "firefox",
  manifest: "manifest.firefox.json",
  target: ["firefox115"],
});
