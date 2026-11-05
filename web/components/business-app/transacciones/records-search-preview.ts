/** Search is limited to identity, the current note and document references. */
export function matchesRecordSearch(query: string, fields: { name: string | null; note: string; documents: readonly string[] }): boolean {
  const normalize = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase().trim();
  const wanted = normalize(query);
  return !wanted || [fields.name ?? "", fields.note, ...fields.documents].some((value) => normalize(value).includes(wanted));
}
