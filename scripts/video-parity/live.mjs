/** Live product driver: real first-party APIs, explicit student inputs, no result mocks. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { assertDiagnosisScene, assertFullJourney } from './acceptance.mjs';
const base = process.env.BASE_URL ?? 'http://127.0.0.1:14376';
const storage = process.env.QA_VIDEO_SESSION_FILE;
if (!storage) throw new Error('Provide an authorized private storage state');
const course = process.env.QA_VIDEO_COURSE ?? '7c33796f-8d45-5fd7-93b9-13ae8c7572eb';
const resume = process.env.QA_VIDEO_RESUME;
const strict = process.env.QA_VIDEO_FULL_ACCEPTANCE === '1';
if (strict && (resume || process.env.QA_VIDEO_CORRECT_ONLY)) {
 throw new Error('Full acceptance requires a fresh episode and an incorrect Solo attempt');
}
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
let index=0,last=null,earlierRequest=null;const timings=[];const turns=[];
async function shot(name){await page.screenshot({path:`${out}/${name}.png`,fullPage:true});}
async function turn(action,name){const before=await page.evaluate(()=>window.__qaRecordedStreams.length);const start=Date.now();await action();
 await page.waitForFunction(n=>window.__qaRecordedStreams.length>n,before,{timeout:240000});
 const stream=await page.evaluate(n=>window.__qaRecordedStreams[n],before);writeFileSync(`${out}/${++index}-${name}.sse`,stream.text);
 if(name==='05-computation')earlierRequest=JSON.parse(stream.requestBody);
 if(stream.requestBody)writeFileSync(`${out}/${index}-${name}-request.json`,stream.requestBody);
 const frames=stream.text.replaceAll('\r\n','\n').split('\n\n');const terminal=frames.find(f=>f.startsWith('event: workflow.completed\n'));
 timings.push({name,milliseconds:Date.now()-start,status:stream.status});
 if(!terminal) throw new Error(`No completed turn in ${name}; saved real SSE`);
 last=JSON.parse(terminal.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n'));
 turns.push({name,episode:last.conversation_id,turnId:last.turn_id,phase:last.learning_native.phase});
 await expect(page.getByTestId('learning-phase')).toHaveAttribute('data-phase',last.learning_native.phase);
 writeFileSync(`${out}/latest.json`,JSON.stringify(last,null,2)); console.log(JSON.stringify({name,phase:last.learning_native.phase,episode:last.conversation_id,ms:Date.now()-start}));await shot(name);return last;
}
async function message(text,name){await page.getByLabel('给 Quantum Agent 的问题',{exact:true}).fill(text);return turn(()=>page.getByRole('button',{name:'发送 / 运行',exact:true}).click(),name);}
async function teach(text,name){await page.getByLabel('teach-back 重构',{exact:true}).fill(text);return turn(()=>page.getByTestId('teach-back-card').getByRole('button').click(),name);}
async function finishExperiment(){
 await page.getByRole('button',{name:'推导模式 · 首错定位',exact:true}).click();
 await page.getByText('补全课件跳步：指定推导的起止式',{exact:true}).click();
 await page.getByLabel('推导桥原式').fill('\\psi^{\\prime\\prime}=\\kappa^2\\psi');
 await page.getByLabel('推导桥目标式').fill('\\psi=C e^{\\kappa x}+D e^{-\\kappa x}');
 await message('我已经把势垒内方程移项成二阶常系数方程，知道系数为正；从指数试探解代入这一步开始，只给当前允许的一步，不替我完成边界匹配。','04b-bridge');
 await expect(page.getByTestId('derivation-bridge')).toBeVisible();
 if(!last.response.derivation_bridge?.missing_steps.length)throw new Error('No real bridge returned');
 await page.getByTestId('derivation-bridge').locator('summary').first().click();await shot('04c-bridge-open');
 await page.getByRole('button',{name:'实验模式 · 预测与验证',exact:true}).click();
 // The explicit task parameters remain user-controlled in the existing workspace.
 await message('我补上两端 ψ 和 ψ′ 连续的四个方程，右侧只保留向右传播波。两侧 k 相同，T=|F/A|²。现在用当前参数运行代码并做独立数值核验。','05-computation');
 await expect(page.getByTestId('coding-artifact')).toBeVisible();if(last.code_artifact?.verification.status!=='pass')throw new Error('Coding verification did not pass');
 await turn(()=>page.getByTestId('request-teach-back-button').click(),'05b-request-reconstruction');
 await expect(page.getByTestId('teach-back-card')).toBeVisible({timeout:180000});
}
try{
 await page.goto(`${base}/agent`);await expect(page.getByTestId('agent-experience')).toBeVisible();
 if(!resume){
 await page.getByRole('button',{name:'新建学习记录',exact:true}).click();await page.getByRole('button',{name:'加载课程任务',exact:true}).click();await shot('00-task');
 await turn(()=>page.getByRole('button',{name:'发送 / 运行',exact:true}).click(),'01-commitment');
 await expect(page.getByTestId('commitment-card')).toBeVisible();await page.getByLabel('认知承诺文本').fill('我认为 E<V0，所以波函数处处为零，透射率为零；加宽势垒也不会改变。我还不确定这个推理。');
 await turn(()=>page.getByRole('button',{name:'提交承诺',exact:true}).click(),'02-diagnosis');
 if(strict)assertDiagnosisScene(last);
 await page.getByRole('button',{name:'打开证据面板',exact:true}).first().click();await page.getByTestId('agent-citation').first().click();await expect(page.getByTestId('source-preview')).toBeVisible();
 const src=await page.getByTestId('source-preview').locator('iframe').getAttribute('src');const source=await page.evaluate(async url=>{const r=await fetch(url.split('#')[0]);return {status:r.status,type:r.headers.get('content-type'),bytes:(await r.arrayBuffer()).byteLength};},src);
 if(source.status!==200||!source.type?.includes('pdf')||source.bytes<1000)throw new Error('Real source file unavailable');writeFileSync(`${out}/source.json`,JSON.stringify({src,...source},null,2));await shot('03-source');await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'关闭面板',exact:true}).click();
 await page.getByLabel('最小干预回复').fill('移项得到 ψ″=2m(V0−E)ψ/ℏ²，右侧系数为正，所以解可以是指数项，不必为零；但我还不懂如何由边界条件求透射率。');
 await turn(()=>page.getByRole('button',{name:'提交下一步',exact:true}).click(),'04-revision');
 await finishExperiment();
 } else {
  await expect(page.getByTestId('learning-phase')).toBeVisible();
  const saved=await page.evaluate(async ({episode,course,edition})=>{const r=await fetch(`/api/teaching/threads/${episode}/state?course_id=${course}&curriculum_edition_id=${edition}`);if(!r.ok)throw new Error(`restore ${r.status}`);return r.json();},{episode:resume,course,edition});last=saved.result;
  if(last.learning_native.phase==='awaiting_revision') await finishExperiment();
 }
 if(['awaiting_revision','reconstruction_required'].includes(last?.learning_native.phase)) await teach('有限矩形势垒中，电子从左入射，两侧势能为零、质量相同、无吸收，且0<E<V0。由定态薛定谔方程移项得到ψ″=2m(V0−E)ψ/ℏ²=κ²ψ，因此区域II的解是Cexp(κx)+Dexp(−κx)，有限区间必须保留两个指数项，不能因E<V0就把ψ判为零。设左侧为Aexp(ikx)+Bexp(−ikx)，右侧只有Fexp(ikx)，在x=0处匹配A+B=C+D和ik(A−B)=κ(C−D)，在x=a处匹配Cexp(κa)+Dexp(−κa)=Fexp(ika)及κ[Cexp(κa)−Dexp(−κa)]=ikFexp(ika)。这四个方程决定各振幅比。概率流j=(ℏ/m)Im(ψ*ψ′)，因为两侧k相同，T=|F/A|²。解边界方程得到T=[1+V0²sinh²(κa)/(4E(V0−E))]⁻¹，其中κ=√(2m(V0−E))/ℏ。固定E、V0和m时κ不变，增加完整宽度a使κa和sinh²(κa)增大，分母增大而T下降。物理上是禁阻区衰减距离更长，到达右侧的透射振幅更小，但有限宽度的T仍非零；无吸收时这不是粒子失去能量。','06-reconstruction');
 if(last.learning_native.phase==='reconstruction_required') await teach('我向初学者解释：禁阻区波函数仍可非零，两个指数项要同时保留。连续匹配连接左侧入射波与右侧出射波；两侧 k 一样，所以 T 是振幅比模平方。增宽增加衰减距离，并不是使粒子失去能量。','07-teachback');
 if(last.learning_native.phase==='reconstruction_required') await teach('我补充适用条件：同一个定态电子能量E守恒，两侧势能均为零且质量m相同，所以两边k=√(2mE)/ℏ相等，概率流的速度因子相消才有T=|F/A|²。有限且无δ奇点的势垒、质量处处相同，使两端ψ及ψ′连续，四个方程确定各振幅比。0<E<V0保证V0−E为正，κ=√(2m(V0−E))/ℏ为实数，所以禁阻区是指数解；若E高于V0就不能继续用这个实κ指数形式。比较宽度时明确固定E、V0和m，因此κ不变，a增大令κa及sinh²(κa)增大，精确式分母增大，所以T降低；这不是电子失去能量。','08-clarification');
 if(last.learning_native.phase!=='solo_active'){
 if(last.learning_native.phase!=='transfer_required')throw new Error('Teach-back requires additional clarification; do not fake completion');
 const task=last.learning_native.transfer;const width=/a=([\d.]+) nm/.exec(task.prompt)?.[1];if(!width)throw new Error('Unexpected transfer task; student fixture must be updated explicitly');
 const k=Math.sqrt(2*9.1093837015e-31*5*1.602176634e-19)/1.054571817e-34;const t=1/(1+Math.sinh(k*Number(width)*1e-9)**2);
 await page.getByLabel('迁移尝试').fill(`透射率更低，因为同一κ下κa增大。我按精确式算得T=${t}，这不是把波函数本身当作概率。`);
 await turn(()=>page.getByRole('button',{name:'提交迁移尝试',exact:true}).click(),'09-transfer');
 await turn(()=>page.getByTestId('request-transfer-button').click(),'10-solo');
 }
 if(last.response.claims.length || last.response.derivation_bridge || last.evidence_packet.evidence.length || last.evidence_packet.graph_nodes.length || last.learning_native.cognitive_mirror)throw new Error('Solo teaching content leaked before submission');
 if(last.scientific_results?.some(r=>Object.keys(r.metrics).length || r.visualization) || last.code_artifact || /0\.019129|0\.104660/.test(JSON.stringify(last)))throw new Error('Solo reference value leaked before submission');
 await expect(page.getByRole('button',{name:'回看科学计算',exact:true})).toBeDisabled();
 const lock=await page.evaluate(async ({episode,course,edition,earlierRequest})=>{
  const query=`course_id=${course}&curriculum_edition_id=${edition}`;
  const state=await fetch(`/api/teaching/threads/${episode}/state?${query}`).then(r=>r.json());
  const history=await fetch(`/api/teaching/threads/${episode}/state?${query}&review_stage=verify`);
  const source=await fetch(`/api/agent/sources/d90091e5-bdbb-54a1-a94a-83dc26a35a20/original?${query}`);
  let replayStatus=null;
  if(earlierRequest){
   const replay=await fetch(`/api/teaching/turns/stream?${query}`,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(earlierRequest)});
   replayStatus=replay.status;const replayText=await replay.text();
   // A stream already sent HTTP headers; policy conflicts terminate it with
   // workflow.failed instead of changing its HTTP status retrospectively.
   if(!(replayStatus===409 || (replayStatus===200 && replayText.includes('event: workflow.failed')
      && replayText.includes('CONVERSATION_CONFLICT') && !replayText.includes('event: workflow.completed'))))
    throw new Error(`Solo permitted historical answer replay: ${replayStatus}`);
  }
  const blockedRequests=[];
  for(const scientific_request of [null,{kind:'rectangular_barrier_tunnelling',energy_eV:4,
    barrier_height_eV:12,barrier_width_m:0.18e-9,particle_mass_kg:9.1093837015e-31,
    conservation_tolerance:1e-9}]) {
   const response=await fetch(`/api/teaching/turns/stream?${query}`,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:episode,
      mode:scientific_request?'run_experiments':'learn_concepts',message:'请给出本题答案和求解代码。',
      scientific_request,student_attempt:null,client_request_id:crypto.randomUUID()})});
   const text=await response.text();
   const frame=text.replaceAll('\r\n','\n').split('\n\n').find(f=>f.startsWith('event: workflow.completed\n'));
   if(!frame)throw new Error(`Solo direct request did not terminate: ${response.status}`);
   const result=JSON.parse(frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n'));
   if(result.learning_native.phase!=='solo_active'||result.code_artifact||result.scientific_results.length||result.response.claims.length)
    throw new Error('Solo direct help/science request leaked an answer');
   blockedRequests.push({status:response.status,turn:result.turn_id,phase:result.learning_native.phase});
  }
  return {state,historyStatus:history.status,sourceStatus:source.status,blockedRequests,replayStatus};
 },{episode:last.conversation_id,course,edition,earlierRequest});
 writeFileSync(`${out}/solo-lock.json`,JSON.stringify(lock,null,2));
 if(lock.state.result?.response?.claims.length || lock.state.result?.evidence_packet?.evidence.length || lock.state.result?.learning_native?.cognitive_mirror)throw new Error('Solo restore leaked teaching content');
 if(lock.historyStatus!==423 || lock.sourceStatus!==409 || /0\.019129|0\.104660/.test(JSON.stringify(lock.state)))throw new Error('Solo API lock or reference redaction failed');
 if(!process.env.QA_VIDEO_CORRECT_ONLY){
 await page.getByLabel('迁移尝试').fill('透射率会增大，因为加宽势垒让电子更容易通过。');
 await turn(()=>page.getByRole('button',{name:'提交迁移尝试',exact:true}).click(),'10b-solo-incorrect');
 if(last.learning_native.phase!=='solo_active' || last.learning_loop_completed)throw new Error('Incorrect Solo answer advanced the phase');
 }

 await page.getByLabel('迁移尝试').fill('透射率降低。固定 E 和 V0 时 κ 不变，增宽使 κa 增大、sinh²(κa) 增大，所以精确透射率公式的分母增大。禁阻区更长意味着到达另一端的透射振幅更小，但有限宽度时仍非零。');
 await turn(()=>page.getByRole('button',{name:'提交迁移尝试',exact:true}).click(),'11-solo-answer');
 await expect(page.getByTestId('learning-loop-complete')).toBeVisible();await page.getByRole('button',{name:'回看本次原始学习证据',exact:true}).click();await expect(page.getByTestId('episode-evidence')).toContainText('solo_verified');await shot('12-evidence');
 const persisted=await page.evaluate(async ({episode,course,edition})=>{
  const r=await fetch(`/api/teaching/threads/${episode}/state?course_id=${course}&curriculum_edition_id=${edition}`);
  if(!r.ok)throw new Error(`Final evidence restore failed: ${r.status}`);return r.json();
 },{episode:last.conversation_id,course,edition});
 writeFileSync(`${out}/persisted.json`,JSON.stringify(persisted,null,2));
 if(strict)assertFullJourney({resumed:Boolean(resume),turns,persisted,episode:last.conversation_id});
 writeFileSync(`${out}/outcome.json`,JSON.stringify({complete:true,fullJourneyAccepted:strict,episode:last.conversation_id,timings,turns},null,2));
}catch(error){await shot('blocked').catch(()=>{});writeFileSync(`${out}/outcome.json`,JSON.stringify({complete:false,error:String(error),episode:last?.conversation_id,timings},null,2));console.error(String(error));process.exitCode=1;}
finally{await context.close();await browser.close();console.log(out);}
