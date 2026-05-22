import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const dist = resolve(root, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

await build({
  entryPoints: [
    resolve(root, "src/background.js"),
    resolve(root, "src/content.js"),
    resolve(root, "src/popup.js"),
  ],
  bundle: true,
  format: "iife",
  target: ["chrome114"],
  outdir: dist,
  logLevel: "info",
});

await cp(resolve(root, "manifest.json"), resolve(dist, "manifest.json"));
await cp(resolve(root, "src/popup.html"), resolve(dist, "popup.html"));

console.log(`Built extension to ${dist}`);
