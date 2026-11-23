import type { PostProcessorModule } from "i18next";

export const dgiiChoiceLabel: PostProcessorModule = {
  type: 'postProcessor',
  name: 'dgiiChoiceLabel',
  process(value, _keys, options) {
    const resolved = options.i18nResolved as { usedKey?: string; res?: unknown } | undefined;
    // The 607 stores Tipo de Ingreso and Tipo Id as one digit; the screen names every DGII list with two.
    const code = /^business\.dgii\.option\.[a-z_]+\.(\d{1,2})$/.exec(resolved?.usedKey ?? '')?.[1];
    return code && typeof resolved?.res === 'string' && resolved.res && value !== code ? `${code.padStart(2, '0')} · ${value}` : value;
  },
};
