declare module "bun:test" {
  type TestCallback = (...args: unknown[]) => unknown | Promise<unknown>;
  type Expectation = {
    not: Expectation;
    resolves: Expectation;
    rejects: Expectation;
    [matcher: string]: Expectation | ((...args: unknown[]) => unknown);
  };
  type TestFunction = {
    (name: string, callback: TestCallback): void;
    each: <Case>(
      cases: readonly Case[],
    ) => (name: string, callback: TestCallback) => void;
  };

  export const describe: TestFunction;
  export const test: TestFunction;
  export const it: TestFunction;
  export function expect(actual: unknown): Expectation;
}

interface ImportMeta {
  readonly dir: string;
}
