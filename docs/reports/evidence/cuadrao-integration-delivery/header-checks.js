async (page) => {
  const results = [];
  const root = '/Users/garces/.codex/worktrees/ff26/private-alpha-next/docs/reports/evidence/cuadrao-integration-delivery';
  for (const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:1000});
    for (const route of ['business','business/en','business/personal','business/en/personal','business/demo','business/en/demo']) {
      await page.goto(`http://127.0.0.1:3223/${route}`);
      await page.evaluate(() => document.fonts.ready);
      const header = page.locator('header');
      const state = await header.evaluate(h => {
        const elements = Array.from(h.querySelectorAll('a,button')).filter(e => e.getBoundingClientRect().width > 0);
        const overlap = elements.some((a,i) => elements.slice(i+1).some(b => {const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();return Math.min(ar.right,br.right)-Math.max(ar.left,br.left)>1 && Math.min(ar.bottom,br.bottom)-Math.max(ar.top,br.top)>1;}));
        return {height:h.getBoundingClientRect().height,overflow:document.documentElement.scrollWidth>innerWidth,overlap};
      });
      if (state.overflow || state.overlap) throw new Error(JSON.stringify({width,route,...state}));
      if (route.endsWith('/demo')) {
        if (width <= 800) await header.locator('button[aria-controls="business-mobile-menu"]').click();
        const back = header.locator('a').filter({hasText:/^(Back to Business|Volver a negocios)$/}).filter({visible:true});
        const detail = await back.evaluate(e => {
          const icon = e.querySelector('svg').getBoundingClientRect();
          const textNode = Array.from(e.childNodes).find(n=>n.nodeType===Node.TEXT_NODE && n.textContent.trim());
          const range = document.createRange(); range.selectNode(textNode); const text=range.getBoundingClientRect();
          return {href:e.getAttribute('href'),iconBefore:icon.right<=text.left,offset:Math.abs(icon.y+icon.height/2-text.y-text.height/2),height:e.getBoundingClientRect().height};
        });
        const expected = route.includes('/en/') ? '/business/en' : '/business';
        if (detail.href !== expected || !detail.iconBefore || detail.offset>2 || detail.height<44) throw new Error(JSON.stringify({width,route,detail}));
        if ([390,1440].includes(width)) await header.screenshot({path:`${root}/${route.includes('/en/')?'en':'es'}-${width}.png`});
        await back.click();
        if (new URL(page.url()).pathname !== expected) throw new Error('Back destination');
        if (width <= 800) {
          await header.locator('button[aria-controls="business-mobile-menu"]').click();
          await page.keyboard.press('Escape');
          if (await header.locator('button[aria-expanded="false"]').count() !== 1) throw new Error('Menu Escape');
        }
        results.push({width,route,...state,...detail});
      } else results.push({width,route,...state});
    }
  }
  return results;
}
