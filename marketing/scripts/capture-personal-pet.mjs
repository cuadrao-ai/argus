import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile, rename } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const baseURL = process.env.MARKETING_CAPTURE_URL ?? 'http://127.0.0.1:4512';
const root = new URL('../../', import.meta.url);
const output = new URL('docs/reports/evidence/cuadrao-marketing-touchup/personal-pet/screens/', root);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const captures = [];
const errors = [];
try {
  for (const viewport of [{width:1440,height:900},{width:390,height:844}]) {
    for (const [route,locale] of [['/personal','es'],['/en/personal','en']]) {
      const record = viewport.width === 1440 && locale === 'es';
      const context = await browser.newContext({viewport,reducedMotion:'no-preference', ...(record ? {recordVideo:{dir:fileURLToPath(output),size:viewport}} : {})});
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      let release;
      const responseGate = new Promise(resolve => {release=resolve;});
      await page.route('**/api/signups', async request => {
        await responseGate;
        await request.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'registered'})});
      });
      await page.goto(new URL(route,baseURL).href);
      await page.evaluate(()=>document.fonts.ready);
      await expect(page.locator('#personal-email')).toBeEnabled();
      await expect(page.locator('figure img').first()).toBeVisible();
      await page.mouse.move(180,300);
      const shot = async (state,fullPage=false) => {
        const file=`personal-${locale}-${viewport.width}-${state}.png`;
        await page.screenshot({path:fileURLToPath(new URL(file,output)),fullPage});
        captures.push({file,route,...viewport,state,mockedSignup:true});
      };
      await shot('idle', viewport.width < 700);
      await page.locator('#personal-email').fill('oops');
      await page.locator('button[type="submit"]').click();
      await expect(page.locator('[data-signup-pet]')).toHaveAttribute('data-pose','checking');
      await expect(page.locator('#signup-error')).toBeVisible();
      await page.waitForTimeout(800);
      await shot('invalid',viewport.width<700);
      await page.locator('#personal-email').fill('preview@example.test');
      await expect(page.locator('[data-signup-pet]')).toHaveAttribute('data-pose','rest');
      await page.getByRole('button',{name:locale==='es'?'Avísame cuando pueda probarla':'Let me know when I can try it'}).click();
      await expect(page.locator('[data-signup-state]')).toHaveAttribute('data-signup-state','submitting');
      if(record){await page.waitForTimeout(400);await shot('pending');}
      release();
      await expect(page.getByRole('heading',{name:locale==='es'?'Ya estás en la lista.':"You're on the list."})).toBeVisible();
      if(record){await page.waitForTimeout(350);await shot('flight');}
      await page.waitForTimeout(1500);
      await shot('success',viewport.width<700);
      if(record) await page.waitForTimeout(700);
      const video=record?page.video():null;
      await context.close();
      if(video) await rename(await video.path(),new URL('personal-signup-demo.webm',output));
    }
  }
} finally {await browser.close();}
if(errors.length)throw new Error(JSON.stringify(errors));
await writeFile(new URL('manifest.json',output),JSON.stringify({sourceCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:fileURLToPath(root),encoding:'utf8'}).trim(),capturedAt:new Date().toISOString(),baseURL,signup:'Browser request intercepted with registered fixture. No signup reached the server or any provider.',browser:'Playwright Chromium headless, isolated contexts',captures},null,2)+'\n');
console.log(fileURLToPath(output));
