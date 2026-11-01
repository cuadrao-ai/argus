import { indexingEnabled } from "./indexing";
import { SITE_ORIGIN } from "./site-routes";

const PUBLIC_HOST = new URL(SITE_ORIGIN).hostname;

// The unfinished landing stays off the public site whatever its settings say.
export function landingPreviewAllowed(host: string | null, indexing: string | undefined): boolean {
  if (!host || indexingEnabled(indexing)) return false;
  const name = host.split(":")[0].toLowerCase();
  return name !== PUBLIC_HOST && !name.endsWith(`.${PUBLIC_HOST}`);
}
