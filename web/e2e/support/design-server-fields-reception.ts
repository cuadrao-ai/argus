export const designServerFieldsReception = {
  root: '[data-testid="reception-preview"]',
  views: '[role="tablist"][aria-label="Vistas de Bandeja"]',
  tabs: {
    all: '#reception-tab-all',
    attention: '#reception-tab-attention',
    listos: '#reception-tab-listos',
  },
  alert: '[role="alert"]',
  empty: '[data-testid="reception-empty"]',
  row: '[data-testid="reception-row"]',
} as const;
