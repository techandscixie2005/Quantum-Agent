/** Read-only visual audit of persisted stages, never a new-journey acceptance. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
const session=process.env.QA_VIDEO_SESSION_FILE;
const episode=process.env.QA_VIDEO_RESUME;
if(!session || !episode)throw new Error('Authorized session and episode are required');
const base=process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const course=process.env.QA_VIDEO_COURSE ?? '7c33796f-8d45-5fd7-93b9-13ae8c7572eb';
const edition=process.env.QA_VIDEO_EDITION ?? '5dd085cb-831c-5ed1-ae01-327f700dc12a';
const out=`docs/implementation/artifacts/video-parity-current/review-${Date.now()}`;
mkdirSync(out,{recursive:true});
const browser=await chromium.launch();const reports=[];
try {
 for(const [width,height] of [[1920,1080],[1366,768]]){
  const context=await browser.newContext({storageState:session,viewport:{width,height}});
  const page=await context.newPage();page.setDefaultTimeout(20000);
  await page.addInitScript(({episode,course,edition})=>{
   localStorage.setItem('qa_course_key',`${course}:${edition}`);localStorage.setItem('qa_conversation_id',episode);
  },{episode,course,edition});
  const start=Date.now();await page.goto(`${base}/agent`);
  await expect(page.getByTestId('learning-loop-complete')).toBeInViewport();
  reports.push({width,stage:'restored',milliseconds:Date.now()-start});
  await page.screenshot({path:`${out}/${width}-completed.png`});
  for(const [stage,label] of [['sources','课程依据'],['bridge','推导补桥'],['verify','科学计算'],['teach_back','Teach-Back'],['transfer','Transfer'],['solo','Solo']]){
   const start=Date.now();await page.getByRole('button',{name:`回看${label}`,exact:true}).click();
   const review=page.getByTestId('stage-review');await expect(review).toContainText('持久记录回看 · 第');
   await expect(review.getByRole('alert')).toHaveCount(0);
   if(stage==='verify')await expect(page.locator('.js-plotly-plot')).toBeVisible({timeout:45000});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);expect(overflow).toBe(false);
   await expect(review.getByRole('button',{name:'返回当前任务'})).toBeInViewport();
   reports.push({width,stage,milliseconds:Date.now()-start,overflow});
   await page.screenshot({path:`${out}/${width}-${stage}.png`});
   if(stage==='sources'){
    const sourceStart=Date.now();const opener=review.getByRole('button',{name:'打开课程来源'}).first();await opener.click();
    const modal=page.getByTestId('source-preview');await expect(modal).toBeVisible();
    await expect(modal).toContainText('自编演示');
    const src=await modal.locator('iframe').getAttribute('src');
    const fetched=await page.evaluate(async url=>{const r=await fetch(url.split('#')[0]);return {status:r.status,type:r.headers.get('content-type'),bytes:(await r.arrayBuffer()).byteLength};},src);
    expect(fetched.status).toBe(200);expect(fetched.type).toContain('pdf');expect(fetched.bytes).toBeGreaterThan(1000);
    reports.push({width,stage:'original-source',openAndFetchMs:Date.now()-sourceStart,...fetched});await page.screenshot({path:`${out}/${width}-source-modal.png`});
    await page.keyboard.press('Escape');await expect(modal).toHaveCount(0);
   }
  }
  await page.getByRole('button',{name:'返回当前任务'}).click();await page.getByRole('button',{name:'回看本次原始学习证据'}).click();
  const evidence=page.getByTestId('episode-evidence');await expect(evidence).toContainText('solo_verified');
  await evidence.locator('summary').first().click();await expect(evidence).toContainText('事件');
  await page.screenshot({path:`${out}/${width}-evidence.png`});await context.close();
 }
} finally {writeFileSync(`${out}/result.json`,JSON.stringify({episode,kind:'historical_stage_review',reports},null,2));await browser.close();console.log(out);}
