import type { PostProcessorModule } from "i18next";

export const dgiiChoiceLabel: PostProcessorModule = {
  type: 'postProcessor',
  name: 'dgiiChoiceLabel',
  process(value, _keys, options) {
    const resolved = options.i18nResolved as { usedKey?: string; res?: unknown } | undefined;
    // The 607 stores Tipo de Ingreso as one digit; the screen names it with two, like every other DGII list.
    const code = /^business\.dgii\.option\.(?:category|payment_method|income_withholding_type|income_type)\.(\d{1,2})$/.exec(resolved?.usedKey ?? '')?.[1];
    return code && typeof resolved?.res === 'string' && resolved.res && value !== code ? `${code.padStart(2, '0')} - ${value}` : value;
  },
};
