/** Live product driver: real first-party APIs, explicit student inputs, no result mocks. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
const base = process.env.BASE_URL ?? 'http://127.0.0.1:14376';
const storage = process.env.QA_VIDEO_SESSION_FILE;
if (!storage) throw new Error('Provide an authorized private storage state');
const course = process.env.QA_VIDEO_COURSE ?? '7c33796f-8d45-5fd7-93b9-13ae8c7572eb';
const resume = process.env.QA_VIDEO_RESUME;
const edition = process.env.QA_VIDEO_EDITION ?? '5dd085cb-831c-5ed1-ae01-327f700dc12a';
const out = `docs/implementation/artifacts/video-parity-live-20260918/run-${Date.now()}`;
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({storageState:storage,viewport:{width:1920,height:1080},recordVideo:{dir:out,size:{width:1920,height:1080}}});
const page = await context.newPage(); page.setDefaultTimeout(20000);
await page.addInitScript(({course,edition,resume})=>{
 localStorage.setItem('qa_course_key',`${course}:${edition}`);
 // New browser process, no existing backend episode is removed.
 if(resume) localStorage.setItem('qa_conversation_id',resume);
 else localStorage.removeItem('qa_conversation_id');
 const original = window.fetch.bind(window); window.__qaRecordedStreams=[];
 window.fetch=async(...args)=>{const response=await original(...args);const url=String(args[0]);
  if(url.includes('/api/teaching/turns/stream')) response.clone().text().then(text=>window.__qaRecordedStreams.push({status:response.status,text,requestBody:args[1]?.body}));
  return response;
 };
},{course,edition,resume});
let index=0,last=null;const timings=[];
async function shot(name){await page.screenshot({path:`${out}/${name}.png`,fullPage:true});}
async function turn(action,name){const before=await page.evaluate(()=>window.__qaRecordedStreams.length);const start=Date.now();await action();
 await page.waitForFunction(n=>window.__qaRecordedStreams.length>n,before,{timeout:240000});
 const stream=await page.evaluate(n=>window.__qaRecordedStreams[n],before);writeFileSync(`${out}/${++index}-${name}.sse`,stream.text);
 if(stream.requestBody)writeFileSync(`${out}/${index}-${name}-request.json`,stream.requestBody);
 const frames=stream.text.replaceAll('\r\n','\n').split('\n\n');const terminal=frames.find(f=>f.startsWith('event: workflow.completed\n'));
 timings.push({name,milliseconds:Date.now()-start,status:stream.status});
 if(!terminal) throw new Error(`No completed turn in ${name}; saved real SSE`);
 last=JSON.parse(terminal.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n'));
 await expect(page.getByTestId('learning-phase')).toHaveAttribute('data-phase',last.learning_native.phase);
 writeFileSync(`${out}/latest.json`,JSON.stringify(last,null,2)); console.log(JSON.stringify({name,phase:last.learning_native.phase,episode:last.conversation_id,ms:Date.now()-start}));await shot(name);return last;
}
async function message(text,name){await page.getByLabel('给 Quantum Agent 的问题',{exact:true}).fill(text);return turn(()=>page.getByRole('button',{name:'发送 / 运行',exact:true}).click(),name);}
try{
 await page.goto(`${base}/agent`);await expect(page.getByTestId('agent-experience')).toBeVisible();
 if(!resume){
 await page.getByRole('button',{name:'新建学习记录',exact:true}).click();await page.getByRole('button',{name:'加载课程任务',exact:true}).click();await shot('00-task');
 await turn(()=>page.getByRole('button',{name:'发送 / 运行',exact:true}).click(),'01-commitment');
 await expect(page.getByTestId('commitment-card')).toBeVisible();await page.getByLabel('认知承诺文本').fill('我认为 E<V0，所以波函数处处为零，透射率为零；加宽势垒也不会改变。我还不确定这个推理。');
 await turn(()=>page.getByRole('button',{name:'提交承诺',exact:true}).click(),'02-diagnosis');
 await page.getByRole('button',{name:'打开证据面板',exact:true}).first().click();await page.getByTestId('agent-citation').first().click();await expect(page.getByTestId('source-preview')).toBeVisible();
 const src=await page.getByTestId('source-preview').locator('iframe').getAttribute('src');const source=await page.evaluate(async url=>{const r=await fetch(url.split('#')[0]);return {status:r.status,type:r.headers.get('content-type'),bytes:(await r.arrayBuffer()).byteLength};},src);
 if(source.status!==200||!source.type?.includes('pdf')||source.bytes<1000)throw new Error('Real source file unavailable');writeFileSync(`${out}/source.json`,JSON.stringify({src,...source},null,2));await shot('03-source');await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'关闭面板',exact:true}).click();
 await page.getByLabel('最小干预回复').fill('移项得到 ψ″=2m(V0−E)ψ/ℏ²，右侧系数为正，所以解可以是指数项，不必为零；但我还不懂如何由边界条件求透射率。');
 await turn(()=>page.getByRole('button',{name:'提交下一步',exact:true}).click(),'04-revision');
 // The explicit task parameters remain user-controlled in the existing workspace.
 await message('我补上两端 ψ 和 ψ′ 连续的四个方程，右侧只保留向右传播波。两侧 k 相同，T=|F/A|²。现在用当前参数运行代码并做独立数值核验。','05-computation');
 await expect(page.getByTestId('coding-artifact')).toBeVisible();if(last.code_artifact?.verification.status!=='pass')throw new Error('Coding verification did not pass');

 } else {
  await expect(page.getByTestId('learning-phase')).toBeVisible();
  await page.getByRole('button',{name:'实验模式 · 预测与验证',exact:true}).click();
 }
 const computations=[];
 for(const [energy,height,width] of [[3.7,9.2,.137],[6.1,11.3,.213],[4.8,13.7,.287]]){
  for(const [label,value] of [['粒子能量',energy],['势垒高度',height],['势垒宽度',width]]){
   await page.getByRole('slider',{name:new RegExp(label)}).evaluate((input,value)=>{
    const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,String(value));input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
   },value);
  }
  await expect(page.getByText('参数已改变：上一任务的曲线与核验已失效。提交当前参数重新计算。')).toBeVisible();
  await expect(page.getByTestId('coding-artifact')).toHaveCount(0);
  await turn(()=>page.getByRole('button',{name:'确定性参考重算',exact:true}).click(),`parameters-${energy}-${height}-${width}`);
  const result=last.scientific_results.find(x=>x.kind==='rectangular_barrier_tunnelling');
  expect(result.status).toBe('pass');expect(last.code_artifact).toBeNull();
  expect(result.metrics.energy_eV).toBe(energy);expect(result.metrics.barrier_height_eV).toBe(height);expect(result.metrics.barrier_width_m).toBeCloseTo(width*1e-9,20);
  const kappa=Math.sqrt(2*9.1093837015e-31*(height-energy)*1.602176634e-19)/1.054571817e-34;
  const expected=1/(1+height*height/(4*energy*(height-energy))*Math.sinh(kappa*width*1e-9)**2);
  expect(result.metrics.T).toBeCloseTo(expected,10);expect(result.metrics.reference_T).toBeCloseTo(expected,10);
  await expect(page.locator('.js-plotly-plot')).toBeVisible({timeout:45000});
  await page.getByRole('button',{name:'Data',exact:true}).click();await expect(page.getByRole('table')).toBeVisible();await shot(`data-${width}`);await page.getByRole('button',{name:'Plot',exact:true}).click();
  computations.push({energy,height,width,inputs_sha256:result.inputs_sha256,rendering_sha256:result.visualization.rendering_sha256,T:result.metrics.T,referenceT:result.metrics.reference_T,execution:"fixed_reference_solver"});
 }
 expect(new Set(computations.map(x=>x.inputs_sha256)).size).toBe(3);
 writeFileSync(`${out}/outcome.json`,JSON.stringify({parameterAcceptance:true,episode:last.conversation_id,computations,timings},null,2));
}catch(error){await shot('blocked').catch(()=>{});writeFileSync(`${out}/outcome.json`,JSON.stringify({parameterAcceptance:false,error:String(error),episode:last?.conversation_id,timings},null,2));console.error(String(error));process.exitCode=1;}
finally{await context.close();await browser.close();console.log(out);}
