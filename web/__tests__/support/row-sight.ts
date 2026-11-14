type Watcher = { callback: IntersectionObserverCallback; targets: Set<Element>; observer: IntersectionObserver };

/** Stands in for the browser saying which rows are on screen. Every row is in sight until a test hides some. */
export function installRowSight() {
  const Original = globalThis.IntersectionObserver;
  const watchers = new Set<Watcher>();
  let hidden: (row: Element) => boolean = () => false;
  const report = (watcher: Watcher) => {
    const entries = [...watcher.targets].filter(target => target.isConnected).map(target => ({ target, isIntersecting: !hidden(target) }) as IntersectionObserverEntry);
    if (entries.length) watcher.callback(entries, watcher.observer);
  };
  globalThis.IntersectionObserver = class {
    private watcher: Watcher;
    constructor(callback: IntersectionObserverCallback) { this.watcher = { callback, targets: new Set(), observer: this as unknown as IntersectionObserver }; }
    observe(target: Element) { watchers.add(this.watcher); this.watcher.targets.add(target); setTimeout(() => { if (watchers.has(this.watcher)) report(this.watcher); }, 0); }
    unobserve(target: Element) { this.watcher.targets.delete(target); }
    disconnect() { watchers.delete(this.watcher); this.watcher.targets.clear(); }
    takeRecords() { return []; }
  } as unknown as typeof IntersectionObserver;
  return {
    /** Rows the predicate names are out of sight from now on. */
    hide: (rows: (row: Element) => boolean) => { hidden = rows; },
    /** Every row is in sight again, and the lists watching hear it. */
    show: () => { hidden = () => false; for (const watcher of [...watchers]) report(watcher); },
    restore: () => { globalThis.IntersectionObserver = Original; },
  };
}
