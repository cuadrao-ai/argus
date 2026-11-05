async (page) => {
 const results=[];
 for (const [port,enabled] of [[3223,true],[3224,false]]) {
  for (const path of ['/business','/business/en','/business/demo','/business/en/demo','/business/personal','/business/en/personal','/business/icon.svg','/business/unknown','/dev/result-card','/privacy','/terms']) {
   const response=await page.request.get(`http://127.0.0.1:${port}${path}`);
   const expected=path.startsWith('/business')&&path!='/business/unknown'?(enabled?200:404):(['/business/unknown','/dev/result-card'].includes(path)?404:200);
   if(response.status()!==expected)throw Error(`${port}${path}: ${response.status()} expected ${expected}`);
   results.push({port,path,status:response.status()});
  }
 }
 await page.goto('http://127.0.0.1:3223/privacy');
 await page.evaluate(()=>localStorage.setItem('i18nextLng','en'));
 for(const [path,lang] of [['/business','es-DO'],['/business/en','en'],['/privacy','en']]){
  await page.goto(`http://127.0.0.1:3223${path}`);
  await page.waitForFunction(expected=>document.documentElement.lang===expected,lang);
  if(await page.evaluate(()=>localStorage.getItem('i18nextLng'))!=='en')throw Error('Marketing changed app language');
 }
 return {results,appLanguage:'English preference preserved across ES/EN marketing and return to privacy'};
}
