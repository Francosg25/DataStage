import { copyFile, mkdir } from "node:fs/promises";
const output = new URL("../public/guides/", import.meta.url);
await mkdir(output, { recursive: true });
await copyFile(
  new URL("../../docs/azure-foundry.md", import.meta.url),
  new URL("azure-foundry.md", output),
);
await copyFile(
  new URL("../../docs/entra-id-primeros-pasos.txt", import.meta.url),
  new URL("microsoft-entra-id.txt", output),
);
