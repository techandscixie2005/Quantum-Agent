/** Real wrong-then-correct teach-back check on an explicitly supplied pending episode. */
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
const episode=process.env.QA_VIDEO_RESUME, storageState=process.env.QA_VIDEO_SESSION_FILE;
if(!episode || !storageState)throw new Error('Pending reconstruction episode and authorized session required');
const query=new URLSearchParams({course_id:process.env.QA_VIDEO_COURSE??'7c33796f-8d45-5fd7-93b9-13ae8c7572eb',curriculum_edition_id:process.env.QA_VIDEO_EDITION??'5dd085cb-831c-5ed1-ae01-327f700dc12a'}).toString();
const out=`docs/implementation/artifacts/flash-teachback-${Date.now()}`;mkdirSync(out,{recursive:true});
const browser=await chromium.launch(), results=[];
try{
 const context=await browser.newContext({storageState}), page=await context.newPage();
 await page.goto(`${process.env.BASE_URL??'http://127.0.0.1:14384'}/agent`);
 const state=await page.evaluate(async ({episode,query})=>fetch(`/api/teaching/threads/${episode}/state?${query}`).then(r=>r.json()),{episode,query});
 assert.equal(state.durable_phase.phase,'reconstruction_required');
 for(const [name,text,phase] of [
  ['wrong','我现在撤回前面的说法，我的最终观点是：E低于势垒时，所有区域的波函数都严格为零；因为电子没有足够能量，透射率必定为零，势垒宽度怎样变化都一样。','reconstruction_required'],
  ['correct','我修正刚才的错误说法：有限矩形势垒的禁阻区可以有非零的指数解，必须保留增长和衰减两项。由薛定谔方程得到κ²=2m(V0−E)/ℏ²。两端的波函数和导数连续，连接左边入射加反射波与右边仅向右传播的波，四个条件确定各振幅比。透射率定义为透射概率流与入射概率流之比；本题两侧零势能、同质量、同一定态能量，所以波数与速度相同，T=|F/A|²。固定E、V0和m时κ不变，完整宽度a增加使禁阻区衰减距离更长、右侧透射振幅更小，因此T降低但有限宽度时不为零；无吸收，能量并未损失。补充相同波数的理由是在解释先前条件，不是在否认它。','transfer_required'],
 ]){
  const started=Date.now(); const textResult=await page.evaluate(async ({episode,query,text})=>{
   const response=await fetch(`/api/teaching/turns/stream?${query}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:episode,mode:'run_experiments',message:'请评价我当前的回讲与修正。',student_attempt:null,scientific_request:null,learning_native:{teach_back:{reconstruction:text,target_concept_ids:[]}},client_request_id:crypto.randomUUID()})});
   if(!response.ok)throw new Error(`HTTP ${response.status}`);
   return response.text();
  },{episode,query,text});
  const frame=textResult.replaceAll('\r\n','\n').split('\n\n').find(f=>f.startsWith('event: workflow.completed\n'));
  assert.ok(frame,'Missing completed response');
  const result=JSON.parse(frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5)).join('\n'));
  results.push({name,episode:result.conversation_id,turn:result.turn_id,phase:result.learning_native.phase,evaluation:result.learning_native.teach_back,milliseconds:Date.now()-started});
  assert.equal(result.learning_native.phase,phase);
 }
}finally{writeFileSync(`${out}/result.json`,JSON.stringify({complete:results.length===2 && results[1].phase==='transfer_required',results},null,2));await browser.close();console.log(out);}
