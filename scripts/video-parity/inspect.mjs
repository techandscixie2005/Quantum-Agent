/** Read-only visual/recovery inspection of a real episode; never mocks APIs. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
const episode=process.env.QA_VIDEO_RESUME;
if(!episode || !process.env.QA_VIDEO_SESSION_FILE) throw new Error('Authorized session and real episode required');
const out=`docs/implementation/artifacts/video-parity-live-20260918/inspection-${Date.now()}`;
mkdirSync(out,{recursive:true});
const browser=await chromium.launch();const reports=[];
try{
for(const width of [1920,1366]){
 const context=await browser.newContext({storageState:process.env.QA_VIDEO_SESSION_FILE,viewport:{width,height:width===1920?1080:768}});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error') errors.push(m.text());});page.on('requestfailed',r=>errors.push(r.url().split('?')[0]+':'+r.failure()?.errorText));
 await page.addInitScript(episode=>{localStorage.setItem('qa_course_key','7c33796f-8d45-5fd7-93b9-13ae8c7572eb:5dd085cb-831c-5ed1-ae01-327f700dc12a');localStorage.setItem('qa_conversation_id',episode);},episode);
 const start=Date.now();await page.goto(new URL('/agent',process.env.BASE_URL??'http://127.0.0.1:3000').href);
 await expect(page.getByTestId('learning-phase')).toBeVisible({timeout:30000});
 const phase=await page.getByTestId('learning-phase').getAttribute('data-phase');const restoreMs=Date.now()-start;
 await page.screenshot({path:`${out}/${width}-restored.png`,fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);expect(overflow).toBe(false);
 const verify=page.getByRole('button',{name:'回看科学计算',exact:true});
 if(phase==='solo_active'){await expect(verify).toBeDisabled();}
 else {await verify.click();await expect(page.getByTestId('coding-artifact')).toBeVisible({timeout:30000}).catch(async e=>{await page.screenshot({path:`${out}/${width}-review-error.png`,fullPage:true});writeFileSync(`${out}/review-error.json`,JSON.stringify({errors,text:await page.locator('body').innerText()},null,2));throw e;});await expect(page.locator('.js-plotly-plot')).toBeVisible({timeout:45000});await page.screenshot({path:`${out}/${width}-calculation.png`,fullPage:true});}
 reports.push({width,phase,restoreMs,overflow,errors});await context.close();
}
}finally{writeFileSync(`${out}/inspection.json`,JSON.stringify({episode,reports},null,2));await browser.close();console.log(out);}
