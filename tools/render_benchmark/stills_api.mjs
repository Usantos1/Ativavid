// EXPERIMENTO 2 (correto) — Remotion por ESTADOS, com bundle reaproveitado.
//
// O CLI `remotion still` reempacota o projeto a cada chamada (medido: 121s no
// primeiro estado). Uma implementacao real empacota UMA vez e reaproveita o
// renderer. Este script mede exatamente isso.
//
// Uso: node stills_api.mjs <dirRemotion> <dirSaida> <frame1,frame2,...>
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";
import fs from "node:fs";

const [remoDir, outDir, framesArg] = process.argv.slice(2);
const frames = framesArg.split(",").map((n) => parseInt(n, 10));
fs.mkdirSync(outDir, { recursive: true });

const t0 = performance.now();
const serveUrl = await bundle({
  entryPoint: path.join(remoDir, "src", "index.ts"),
  webpackOverride: (c) => c,
});
const tBundle = (performance.now() - t0) / 1000;

const t1 = performance.now();
const composition = await selectComposition({ serveUrl, id: "Reels", inputProps: {} });
const tSelect = (performance.now() - t1) / 1000;

const per = [];
for (let i = 0; i < frames.length; i++) {
  const s = performance.now();
  await renderStill({
    composition,
    serveUrl,
    output: path.join(outDir, `state_${String(i).padStart(3, "0")}.png`),
    frame: frames[i],
    imageFormat: "png",
    logLevel: "error",
  });
  per.push((performance.now() - s) / 1000);
}

const sorted = [...per].sort((a, b) => a - b);
const med = sorted[Math.floor(sorted.length / 2)];
const total = tBundle + tSelect + per.reduce((a, b) => a + b, 0);

console.log(JSON.stringify({
  bundle_s: +tBundle.toFixed(2),
  select_s: +tSelect.toFixed(2),
  estados: per.length,
  primeiro_s: +per[0].toFixed(2),
  mediana_s: +med.toFixed(2),
  soma_estados_s: +per.reduce((a, b) => a + b, 0).toFixed(2),
  total_s: +total.toFixed(2),
}));
