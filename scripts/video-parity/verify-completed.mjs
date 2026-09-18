import {chromium,expect} from '@playwright/test';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
const episode=process.env.QA_VIDEO_RESUME;
if(!episode || !process.env.QA_VIDEO_SESSION_FILE)throw new Error('Authorized session and completed episode required');
const out=`docs/implementation/artifacts/video-parity-live-20260918/recovery-${Date.now()}`;mkdirSync(out,{recursive:true});
const b=await chromium.launch();
try{
 const c=await b.newContext({storageState:process.env.QA_VIDEO_SESSION_FILE,viewport:{width:1366,height:768}});const p=await c.newPage();
 await p.addInitScript(episode=>{localStorage.setItem('qa_course_key','7c33796f-8d45-5fd7-93b9-13ae8c7572eb:5dd085cb-831c-5ed1-ae01-327f700dc12a');localStorage.setItem('qa_conversation_id',episode);},episode);
 const query='course_id=7c33796f-8d45-5fd7-93b9-13ae8c7572eb&curriculum_edition_id=5dd085cb-831c-5ed1-ae01-327f700dc12a';
 const start=Date.now();await p.goto(new URL('/agent',process.env.BASE_URL ?? 'http://127.0.0.1:3000').href);await expect(p.getByTestId('learning-loop-complete')).toBeVisible({timeout:30000});const recoveryMs=Date.now()-start;
 const read=()=>p.evaluate(async url=>{const r=await fetch(url);if(!r.ok)throw new Error(`state ${r.status}`);return r.json();},`/api/teaching/threads/${episode}/state?${query}`);
 const before=await read();expect(before.durable_phase.phase).toBe('complete');expect(before.result.learning_loop_completed).toBe(true);
 const kinds=before.learning_evidence.map(x=>x.kind);for(const kind of ['commitment','teach_back','transfer_verified','solo_verified'])expect(kinds).toContain(kind);
 expect(JSON.stringify(before.learning_evidence)).toContain('E<V0，所以波函数处处为零');
 writeFileSync(`${out}/state.json`,JSON.stringify(before,null,2));
 let retries=[];
 if(process.env.QA_VIDEO_REPLAY_REQUEST){const payload=readFileSync(process.env.QA_VIDEO_REPLAY_REQUEST,'utf8');
 retries=await p.evaluate(async({query,payload})=>Promise.all([0,1].map(async()=>{const r=await fetch(`/api/teaching/turns/stream?${query}`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'text/event-stream'},body:payload});return {status:r.status,text:await r.text()};})),{query,payload});
 for(const r of retries){expect(r.status).toBe(200);expect(r.text).toContain(before.turn_id);expect(r.text).toContain('workflow.completed');}
 const after=await read();expect(after.learning_evidence.map(x=>x.id)).toEqual(before.learning_evidence.map(x=>x.id));expect(after.turn_id).toBe(before.turn_id);
 }
 await p.reload();await expect(p.getByTestId('learning-loop-complete')).toBeVisible();await p.getByRole('button',{name:'回看本次原始学习证据',exact:true}).click();await expect(p.getByTestId('episode-evidence')).toContainText('solo_verified');await p.screenshot({path:`${out}/completed.png`,fullPage:true});
 writeFileSync(`${out}/result.json`,JSON.stringify({episode,recoveryMs,phase:before.durable_phase.phase,evidenceCount:kinds.length,replayed:retries.length,turnId:before.turn_id},null,2));
}finally{await b.close();console.log(out);}
