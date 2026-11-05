let generation = 0;
let logoutGeneration = 0;
let owner: string | null | undefined;

export function browserAuthGeneration(): number { return generation; }
export function browserLogoutGeneration(): number { return logoutGeneration; }
export function invalidateBrowserAuth(): void { generation += 1; logoutGeneration += 1; }
export function observeBrowserAuth(userId: string | null): void {
  if (owner !== undefined && owner !== userId) generation += 1;
  owner = userId;
}
export function requireBrowserAuthGeneration(expected: number): void {
  if (generation !== expected) throw new Error("Browser session changed");
}
