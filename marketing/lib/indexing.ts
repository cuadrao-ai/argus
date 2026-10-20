// Search indexing is a runtime property of the host, never of the build, so a
// preview or candidate host stays excluded until the public host sets it.
export function indexingEnabled(value: string | undefined): boolean {
  return value === "public";
}

// A private host still publishes these two pages, so they skip the site-wide
// robots header. One trailing slash is the same path.
export const PRIVATE_HOST_INDEXABLE_PATHS = ["/eliminar-datos", "/privacidad"] as const;

export function omitsPrivateHostRobotsHeader(pathname: string): boolean {
  const bare = pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  return PRIVATE_HOST_INDEXABLE_PATHS.some((path) => path === bare);
}
