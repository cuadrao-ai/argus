import { copyFile, mkdir } from "node:fs/promises";

const destination = new URL("../public/cuadrao-site/", import.meta.url);
await mkdir(destination, { recursive: true });
for (const asset of ["cuadrao-lockup-light.svg", "cuadrao-lockup-dark.svg", "cuadrao-mark-light.svg"]) {
  await copyFile(new URL(`../brand/${asset}`, import.meta.url), new URL(asset, destination));
}
