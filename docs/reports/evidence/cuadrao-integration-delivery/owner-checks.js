async (page) => {
  const results = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const root = '/Users/garces/.codex/worktrees/ff26/private-alpha-next/docs/reports/evidence/cuadrao-integration-delivery';
  const fit = async (label) => {
    const excess = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, panels: [...document.querySelectorAll('[role="tabpanel"]')].filter(e => e.getBoundingClientRect().width).map(e => ({ id: e.id, width: e.clientWidth, content: e.scrollWidth })) }));
    assert(excess.document <= excess.viewport + 1, `${label}: document overflow ${JSON.stringify(excess)}`);
    assert(excess.panels.every(p => p.content <= p.width + 1), `${label}: panel overflow ${JSON.stringify(excess)}`);
  };
  for (const locale of ['es', 'en']) {
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`http://127.0.0.1:3223/business${locale === 'en' ? '/en' : ''}`);
      await page.locator('#money-tab-position').waitFor();
      await page.evaluate(() => document.fonts.ready);
      for (const [story, steps] of [['money', ['position', 'movements', 'separation']], ['plan', ['upcoming', 'budgets', 'outlook']], ['work', ['capture', 'assistant', 'search', 'updates']]]) {
        for (const step of steps) {
          await page.locator(`#${story}-tab-${step}`).click();
          assert(await page.locator(`#${story}-tab-${step}`).getAttribute('aria-selected') === 'true', `${story}/${step} selection`);
          await fit(`${locale}/${width}/${story}/${step}`);
        }
      }
      results.push(`${locale}/${width}: 10 selected states fit`);
      if (locale === 'es' && [390, 1440].includes(width)) {
        for (const [story, step] of [['money', 'position'], ['money', 'separation'], ['plan', 'budgets'], ['plan', 'outlook'], ['work', 'assistant']]) {
          await page.locator(`#${story}-tab-${step}`).click();
          await page.locator(`#${story}-panel`).screenshot({ path: `${root}/${story}-${step}-${width}.png` });
        }
      }
    }
    const es = locale === 'es';
    await page.locator('#money-tab-position').click();
    assert((await page.locator('#money-panel').innerText()).includes('79,700'), 'DOP cash');
    await page.locator('#money-panel').getByRole('button', { name: 'USD', exact: true }).click();
    assert((await page.locator('#money-panel').innerText()).includes('900'), 'USD cash');
    assert(!(await page.locator('#money-panel').innerText()).includes('79,700'), 'currencies kept separate');
    await page.locator('#money-panel').getByRole('button', { name: 'DOP', exact: true }).click();
    await page.locator('#money-tab-position').focus();
    await page.keyboard.press('ArrowDown');
    assert(await page.locator('#money-tab-movements').getAttribute('aria-selected') === 'true', 'roving keyboard tabs');
    await page.keyboard.press('End');
    assert(await page.locator('#money-tab-separation').getAttribute('aria-selected') === 'true', 'End selects last tab');
    await page.locator('#plan-tab-outlook').click();
    const scenarios = page.locator('#plan-panel').getByRole('button');
    await scenarios.nth(0).click();
    assert((await page.locator('#plan-panel').innerText()).includes('71,200'), 'base forecast');
    await scenarios.nth(1).click();
    assert((await page.locator('#plan-panel').innerText()).includes('41,200'), 'delayed forecast');
    assert((await page.locator('#plan-panel').innerText()).includes('79,700'), 'actual cash unchanged');
    await page.locator('#work-tab-capture').click();
    const work = page.locator('#work-panel');
    for (const method of es ? ['Manual', 'Texto', 'Voz', 'Foto', 'Archivo'] : ['Manual', 'Text', 'Voice', 'Photo', 'File']) {
      await work.getByRole('button', { name: method, exact: true }).click();
      assert(await work.getByRole('button', { name: method, exact: true }).getAttribute('aria-pressed') === 'true', `input ${method}`);
    }
    await work.getByRole('button', { name: es ? 'Revisar propuesta' : 'Review proposal', exact: true }).click();
    await page.locator('#capture-description').fill('Internet local revisado');
    await page.locator('#capture-amount').fill('1650');
    await page.locator('#capture-category').selectOption('unclassified');
    await work.getByRole('button', { name: es ? 'Confirmar ejemplo' : 'Confirm example', exact: true }).click();
    assert((await work.getByRole('status').innerText()).includes('1,650'), 'reviewed amount confirmed');
    assert((await work.innerText()).includes(es ? 'No se guardó un movimiento real' : 'No actual movement was saved'), 'capture honesty');
    await page.locator('#work-tab-assistant').click();
    assert((await work.innerText()).includes('30,000') && (await work.innerText()).includes('18,000'), 'assistant grounded amounts');
    await work.getByRole('button', { name: es ? 'Proponer un recordatorio' : 'Propose a reminder', exact: true }).click();
    await page.locator('#reminder-date').fill('2026-10-15');
    await page.locator('#reminder-note').fill('Revisar saldo acordado');
    await work.getByRole('button', { name: es ? 'Confirmar recordatorio de ejemplo' : 'Confirm sample reminder', exact: true }).click();
    assert((await work.getByRole('status').innerText()).includes('Revisar saldo acordado'), 'edited reminder confirmed');
    await page.locator('#work-tab-search').click();
    await page.locator('#record-search').fill('La Ceiba');
    await work.getByRole('button', { name: es ? /^Factura 1024/ : /^Invoice 1024/ }).click();
    assert((await work.innerText()).includes('48,000'), 'search record opened');
    await work.getByRole('button', { name: es ? 'Volver a resultados' : 'Back to results', exact: true }).click();
    assert(await page.locator('#record-search').inputValue() === 'La Ceiba', 'query preserved');
    await page.locator('#record-search').fill('no-such-record');
    assert((await work.innerText()).includes(es ? 'No hay resultados' : 'No matches'), 'empty search');
    await page.locator('#work-tab-updates').click();
    await work.getByRole('link', { name: es ? 'Ver próximos pagos' : 'View upcoming payments', exact: true }).click();
    assert(await page.locator('#plan-tab-upcoming').getAttribute('aria-selected') === 'true', 'update opens upcoming state');
    await page.locator('#work-tab-updates').click();
    await work.getByRole('link', { name: es ? 'Revisar documento' : 'Review document', exact: true }).click();
    assert(await page.locator('#expense-tab-missing').isVisible(), 'receipt deep link opens details');
    for (const step of ['missing', 'review', 'linked']) {
      await page.locator(`#expense-tab-${step}`).click();
      assert(await page.locator(`#expense-tab-${step}`).getAttribute('aria-selected') === 'true', 'receipt step');
    }
    for (const step of [0, 1, 2]) await page.locator(`#record-tab-${step}`).click();
    assert((await page.locator('#record-panel').innerText()).includes('30,000'), 'invoice balance preserved');
    results.push(`${locale}: currencies, keyboard, forecast, five capture methods, edited confirmation, assistant reminder, search return, update destinations, receipt and invoice pass`);
  }
  assert(errors.length === 0, `page errors: ${errors.join('; ')}`);
  return { results, pageErrors: errors, note: 'Only labelled local examples exercised; no contact or waitlist submissions.' };
}
