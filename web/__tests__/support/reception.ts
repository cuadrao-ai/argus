/** Queries over the Reception list as a person reads it. */
export const receptionRows = (host: ParentNode) => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')];

/** The document title the row's identity button shows, without the screen-reader "No visto" lead. */
export const rowTitle = (row: Element) => (row.querySelector("button")?.textContent ?? "").replace(/^No visto:\s*/, "");

export const rowTitles = (host: ParentNode) => receptionRows(host).map(rowTitle);

export const receptionTab = (host: ParentNode, key: "all" | "review" | "processing" | "attention") => host.querySelector<HTMLButtonElement>(`#reception-tab-${key}`);

/** The number beside a view's name; null where the view shows none. */
export const tabCount = (host: ParentNode, key: "review" | "processing" | "attention") => receptionTab(host, key)?.querySelector("span")?.textContent ?? null;

export const rowState = (row: Element) => row.querySelector('[data-testid="status-pill"]')?.textContent ?? "";
