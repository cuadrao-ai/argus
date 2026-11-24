/** The tags the legacy status pill draws. `reason` is a code the server sent. */
export type ReceptionTag =
  | { tag: "reading" }
  | { tag: "attention"; reason: string | null }
  | { tag: "listo" }
  | { tag: "approved" }
  | { tag: "dismissed" };
