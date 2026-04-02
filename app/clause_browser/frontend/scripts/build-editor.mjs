import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");
const outdir = path.join(frontendRoot, "static", "js", "vendor");

await mkdir(outdir, { recursive: true });

await build({
  entryPoints: [path.join(frontendRoot, "src", "tinymce-editor.js")],
  outfile: path.join(outdir, "tinymce-editor.js"),
  bundle: true,
  format: "esm",
  target: "es2020",
  sourcemap: false,
  minify: false,
  logLevel: "info",
});
