export function runActionIdempotencyKey(input: {
  type: string;
  payload?: Record<string, unknown>;
}): string | null {
  if (input.type !== "run_backtest") return null;
  const explicitKey = input.payload?.idempotency_key;
  if (typeof explicitKey === "string" && explicitKey.trim()) {
    return explicitKey.trim();
  }
  const confirmationId = input.payload?.confirmation_id;
  return typeof confirmationId === "string" && confirmationId.trim()
    ? confirmationId.trim()
    : null;
}
