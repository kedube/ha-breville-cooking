import * as esbuild from "esbuild";
import { fileURLToPath } from "node:url";

// The integration serves the bundle from custom_components/breville_cooking/frontend/, and the
// release zips that folder, so the committed file ships as is. Nothing version-specific is baked
// in: the URL's ?v= stamp changes with every build, so bumping manifest.json for a release never
// makes the committed bundle stale.
await esbuild.build({
  absWorkingDir: fileURLToPath(new URL(".", import.meta.url)),
  entryPoints: ["src/breville-cooking-panel.ts"],
  bundle: true,
  format: "esm",
  target: "es2021",
  outfile: "../custom_components/breville_cooking/frontend/breville-cooking-panel.js",
  minify: true,
  legalComments: "none",
  logLevel: "info",
});
