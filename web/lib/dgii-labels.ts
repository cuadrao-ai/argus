import type { PostProcessorModule } from "i18next";

export const dgiiChoiceLabel: PostProcessorModule = {
  type: 'postProcessor',
  name: 'dgiiChoiceLabel',
  process(value, _keys, options) {
    const resolved = options.i18nResolved as { usedKey?: string; res?: unknown } | undefined;
    const code = /^business\.dgii\.option\.(?:category|payment_method)\.(\d{2})$/.exec(resolved?.usedKey ?? '')?.[1];
    return code && typeof resolved?.res === 'string' && resolved.res && value !== code ? `${code} - ${value}` : value;
  },
};
