export const MOCK_PORT = Number(process.env.MARKETING_E2E_MOCK_PORT ?? 4510);
export const SITE_PORT = Number(process.env.MARKETING_E2E_SITE_PORT ?? 4511);
export const PUBLIC_PORT = Number(
  process.env.MARKETING_E2E_PUBLIC_PORT ?? 4512,
);
export const MOCK_URL = `http://127.0.0.1:${MOCK_PORT}`;
export const PUBLIC_URL = `http://127.0.0.1:${PUBLIC_PORT}`;
