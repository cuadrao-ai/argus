export function tFromCatalog(catalog: Record<string, unknown>) {
  return (key: string, options?: Record<string, unknown> | string) => {
    const values =
      typeof options === "object" && options !== null
        ? options
        : ({} as Record<string, unknown>);
    const count = values.count;
    const pluralKey =
      typeof count === "number"
        ? count === 1
          ? `${key}_one`
          : `${key}_other`
        : key;
    const template = pluralKey
      .split(".")
      .reduce<unknown>(
        (value, segment) =>
          typeof value === "object" && value !== null && !Array.isArray(value)
            ? (value as Record<string, unknown>)[segment]
            : undefined,
        catalog,
      );
    if (typeof template !== "string") {
      return key;
    }
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
      String(values[name] ?? ""),
    );
  };
}
