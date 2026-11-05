const SIGN_IN_BY_HOST: Record<string, string> = {
  "cuadrao.ai": "https://cuadrao-app-y7m5.onrender.com/?auth=login",
  "www.cuadrao.ai": "https://cuadrao-app-y7m5.onrender.com/?auth=login",
  "cuadrao-marketing-staging.onrender.com": "https://cuadrao-web-staging.onrender.com/?auth=login",
};

export function businessSignInHref(hostname: string): string | null {
  return Object.hasOwn(SIGN_IN_BY_HOST, hostname) ? SIGN_IN_BY_HOST[hostname] : null;
}
