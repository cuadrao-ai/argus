// Search indexing is a runtime property of the host, never of the build, so a
// preview or candidate host stays excluded until the public host sets it.
export function indexingEnabled(value: string | undefined): boolean {
  return value === "public";
}
