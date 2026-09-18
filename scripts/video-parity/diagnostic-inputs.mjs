/** Real semantic variation checks. Explicit student fixtures, never product answers. */
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
const storageState=process.env.QA_VIDEO_SESSION_FILE;
if(!storageState)throw new Error('Authorized private session required');
const base=process.env.BASE_URL??'http://127.0.0.1:3000';
const query=new URLSearchParams({course_id:process.env.QA_VIDEO_COURSE??'7c33796f-8d45-5fd7-93b9-13ae8c7572eb',curriculum_edition_id:process.env.QA_VIDEO_EDITION??'5dd085cb-831c-5ed1-ae01-327f700dc12a'});
const cases=[
 ['correct','有限势垒且0<E<V0时禁阻区可有非零指数解，匹配两端波函数和导数得到透射振幅；固定能量和势垒高度时，增加完整宽度使透射率降低。','no_clear_error'],
 ['wrong','因为电子能量小于势垒高度，所以波函数在所有位置都为零，透射率严格等于零。','physical_interpretation_error'],
 ['paraphrase','粒子跨不过这个能量门槛，故任何区域都不可能有概率振幅，右侧通过的概率只能是零。','physical_interpretation_error'],
 ['partial','我移项得ψ″=κ²ψ，κ²为正，所以指数解可以非零；我还不会连接左右边界。',null],
 ['unknown','我还不知道如何判断，也暂时写不出推导。',null],
];
const out=`docs/implementation/artifacts/video-parity-completion/diagnostic-inputs-${Date.now()}`;mkdirSync(out,{recursive:true});
const browser=await chromium.launch();const results=[];
try{
 const context=await browser.newContext({storageState});const page=await context.newPage();await page.goto(`${base}/agent`);
 for(const [name,student_attempt,kind] of cases){
  const start=Date.now();const stream=await page.evaluate(async ({query,student_attempt})=>{
   const r=await fetch(`/api/teaching/turns/stream?${query}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:null,scientific_request:{kind:'rectangular_barrier_tunnelling',energy_eV:5,barrier_height_eV:10,barrier_width_m:0.1e-9,particle_mass_kg:9.1093837015e-31,conservation_tolerance:1e-9},scientific_execution:'reference_only',mode:'run_experiments',message:'有限矩形势垒，电子左入射，两侧零势能且同质量，无吸收，0<E<V0。请只诊断我的当前判断，不代写答案。',student_attempt,client_request_id:crypto.randomUUID()})});
   return {status:r.status,text:await r.text()};
  },{query:query.toString(),student_attempt});
  writeFileSync(`${out}/${name}.sse`,stream.text);
  const f=stream.text.replaceAll('\r\n','\n').split('\n\n').find(f=>f.startsWith('event: workflow.completed\n'));
  if(stream.status!==200||!f)throw new Error(`No completed diagnosis in ${name}: HTTP ${stream.status}`);
  const result=JSON.parse(f.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n'));
  writeFileSync(`${out}/${name}.json`,JSON.stringify(result,null,2));
  if(kind){assert.equal(result.diagnosis.status,'model_inference');assert.equal(result.diagnosis.first_error?.kind,kind);}
  if(name==='unknown')assert.ok(['inconclusive','no_clear_error',undefined].includes(result.diagnosis.first_error?.kind));
  if(name==='partial')assert.notEqual(result.diagnosis.first_error?.kind,'physical_interpretation_error');
  results.push({name,milliseconds:Date.now()-start,episode:result.conversation_id,turn:result.turn_id,diagnosis:result.diagnosis});
 }
 assert.equal(new Set(results.map(r=>r.diagnosis.summary)).size,cases.length);
}finally{writeFileSync(`${out}/result.json`,JSON.stringify({complete:results.length===cases.length,results},null,2));await browser.close();console.log(out);}
