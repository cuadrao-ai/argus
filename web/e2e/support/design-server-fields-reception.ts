export const designServerFieldsReception = {
  root: '[data-testid="reception-preview"]',
  views: '[data-testid="bandeja-segments"]',
  tabs: {
    all: '#reception-tab-all',
    review: '#reception-tab-review',
    processing: '#reception-tab-processing',
    attention: '#reception-tab-attention',
  },
  alert: '[role="alert"]',
  empty: '[data-testid="reception-empty"]',
  row: '[data-testid="reception-row"]',
} as const;
