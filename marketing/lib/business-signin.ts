export function businessSignInHref(hostname: string): string | null {
  return hostname === "cuadrao-marketing-staging.onrender.com"
    ? "https://cuadrao-web-staging.onrender.com/?auth=login"
    : null;
}
