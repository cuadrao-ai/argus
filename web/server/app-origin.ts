export function appOrigin(env: NodeJS.ProcessEnv = process.env): string | undefined {
  return env.CUADRAO_APP_ORIGIN ?? env.ARGUS_APP_ORIGIN;
}
