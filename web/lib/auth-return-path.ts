/**
 * Where sign-in sends someone back to, when they arrived at a page other than
 * chat. Only listed paths and their listed query keys survive, so the value can
 * never become an open redirect or carry arbitrary state.
 */
const RETURNABLE: Readonly<Record<string, readonly string[]>> = {
  "/biz": ["view", "receipt", "conversation", "draft"],
};

const VALUE = /^[A-Za-z0-9_-]{1,128}$/;

function allowedPath(path: string, params: URLSearchParams): string | undefined {
  const keys = RETURNABLE[path];
  if (!keys) return undefined;
  const kept = new URLSearchParams();
  for (const key of keys) {
    const value = params.get(key);
    if (value && VALUE.test(value)) kept.set(key, value);
  }
  const query = kept.toString();
  return query ? `${path}?${query}` : path;
}

export function returnPathFor(
  landingPath: string | undefined,
  search: URLSearchParams,
): string | undefined {
  return landingPath ? allowedPath(landingPath, search) : undefined;
}

export function readReturnPath(search: string): string | undefined {
  const raw = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search).get("return_to");
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return undefined;
  try {
    const url = new URL(raw, "http://return.invalid");
    if (url.origin !== "http://return.invalid") return undefined;
    return allowedPath(url.pathname, url.searchParams);
  } catch {
    return undefined;
  }
}
