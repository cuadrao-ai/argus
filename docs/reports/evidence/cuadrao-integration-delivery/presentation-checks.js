async (page) => {
 const root='/Users/garces/.codex/worktrees/ff26/private-alpha-next/docs/reports/evidence/cuadrao-integration-delivery';
 const results=[]; const errors=[];
 page.on('pageerror', e=>errors.push(e.message));
 const check=(v,m)=>{if(!v)throw Error(m)};
 await page.emulateMedia({reducedMotion:'reduce'});
 for(const locale of ['es','en']) for(const kind of ['business','personal','demo']) for(const width of [320,390,768,1440]) {
  await page.setViewportSize({width,height:1000});
  const path=`/business${locale==='en'?'/en':''}${kind==='business'?'':'/'+kind}`;
  const response=await page.goto('http://127.0.0.1:3223'+path);
  check(response.status()===200, path+' status');
  await page.evaluate(()=>document.fonts.ready);
  const state=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,brokenImages:[...document.images].filter(i=>i.complete&&i.naturalWidth===0).map(i=>i.src),badAnchors:[...document.querySelectorAll('a[href^="#"]')].map(a=>a.getAttribute('href')).filter(h=>h.length>1&&!document.getElementById(h.slice(1))),title:document.title,og:document.querySelector('meta[property="og:image"]')?.content,twitter:document.querySelector('meta[name="twitter:card"]')?.content,robots:document.querySelector('meta[name="robots"]')?.content}));
  check(state.scroll<=width+1,path+' overflow');check(!state.badAnchors.length,path+' missing anchors');check(!state.brokenImages.length,path+' broken images');check(state.title.split('Cuadrao').length===2,path+' repeated brand');check(state.og.endsWith(`share-${kind==='personal'?'personal':'business'}-${locale}.png`),path+' sharing image');check(state.twitter==='summary_large_image',path+' twitter');check(state.robots.includes('noindex'),path+' preview indexing');
  if(kind==='business'){
   check(await page.locator('#preguntas details').count()===5,'FAQ count');
   for(const summary of await page.locator('#preguntas summary').all())await summary.click();
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'expanded FAQ overflow');
   check(await page.locator('footer a[href^="mailto:"]').count()===0,'duplicate footer email');
   if(width===390||width===1440){await page.locator('#nosotros').screenshot({path:`${root}/founder-${locale}-${width}.png`});await page.locator('#preguntas').screenshot({path:`${root}/faq-${locale}-${width}.png`});}
  }
  if(kind==='personal'){
   const order=await page.evaluate(()=>{const input=document.querySelector('#personal-email'),art=document.querySelector('main figure');return{dom:!!(input.compareDocumentPosition(art)&Node.DOCUMENT_POSITION_FOLLOWING),input:input.getBoundingClientRect().bottom,art:art.getBoundingClientRect().top}});
   check(order.dom,'personal DOM');if(width<=700)check(order.input<order.art,'personal visual order');
   check(await page.locator('#signup-local').isVisible(),'signup local disclosure');
  }
  if(kind==='demo'){
   const order=await page.evaluate(()=>{const form=document.querySelector('main form'),aside=document.querySelector('main aside');return{dom:!!(form.compareDocumentPosition(aside)&Node.DOCUMENT_POSITION_FOLLOWING),form:form.getBoundingClientRect().bottom,aside:aside.getBoundingClientRect().top}});
   check(order.dom,'contact DOM');if(width<=700)check(order.form<order.aside,'contact visual order');
   check(await page.locator('#demo-local-notice').isVisible(),'contact local disclosure');
  }
  if([390,1440].includes(width)){
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${root}/${kind}-${locale}-${width}.png`});
   if(kind!=='business')await page.screenshot({path:`${root}/${kind}-${locale}-${width}-full.png`,fullPage:true});
  }
  results.push({path,width,height:state.height,title:state.title});
 }
 for(const locale of ['es','en']){
  await page.goto(`http://127.0.0.1:3223/business${locale==='en'?'/en':''}/demo`);
  await page.locator('main button[type="submit"]').click();check(await page.locator('#demo-name').getAttribute('aria-invalid')==='true','required contact name');
  await page.locator('#demo-name').fill('Local presentation check');await page.locator('#demo-email').fill('presentation@example.com');
  await page.locator('main button[type="submit"]').click();await page.locator('#demo-review-title').waitFor();await page.waitForFunction(()=>document.activeElement?.id==='demo-review-title');check(await page.locator('#demo-review-title').evaluate(e=>document.activeElement===e),'review focus');
  check((await page.locator('main').innerText()).includes(locale==='es'?'No se ha enviado':'Nothing has been sent'),'contact review disclosure');
 }
 await page.goto('http://127.0.0.1:3223/business/en/personal');

 await page.locator('#personal-email').fill('presentation@example.com');await page.locator('main button[type="submit"]').click();await page.locator('#signup-error').waitFor();check(await page.locator('#personal-email').inputValue()==='presentation@example.com','signup retry preserves email');
 check(!errors.length,errors.join(';'));
 return{results,errors,checks:'24 page/layout/metadata checks, FAQ/anchors, mobile DOM and visual order, local contact validation/review focus, real unavailable signup endpoint. No signup saved and no email sent.'};
}
