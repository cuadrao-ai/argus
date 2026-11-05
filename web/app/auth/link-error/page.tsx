import { AuthLinkErrorClient } from "@/components/status/AuthLinkErrorClient";
import { mapAuthLinkError } from "@/lib/auth-link-error";
import { referenceCode } from "@/lib/failure-screen";

export default async function AuthLinkErrorPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string") search.set(key, value);
  }
  const view = mapAuthLinkError({
    search: search.toString() ? `?${search.toString()}` : "",
    hash: "",
    pathname: "/auth/link-error",
  });
  return <AuthLinkErrorClient view={view} reference={referenceCode(null)} />;
}
