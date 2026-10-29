// Next publishes this one nonsecret server setting at build time. The fallback
// is the 180-second turn window used by the deployed runtime configuration.
const configuredSeconds = Number(process.env.CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS);
export const CHAT_RUNTIME_EVENT_TIMEOUT_MS = (
  Number.isFinite(configuredSeconds) && configuredSeconds >= 1 ? configuredSeconds : 180
) * 1_000;
