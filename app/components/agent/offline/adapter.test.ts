import assert from "node:assert/strict";
import { test } from "node:test";
import { createDemoAdapter, samples } from "./adapter";
import { parseTeachingTurnResult } from "../../teaching/contracts";
const values = new Map<string,string>();
Object.defineProperty(globalThis, "sessionStorage", {value:{getItem:(k:string)=>values.get(k)??null,setItem:(k:string,v:string)=>values.set(k,v),removeItem:(k:string)=>values.delete(k)},configurable:true});
Object.defineProperty(globalThis, "window", {value:{location:{origin:"http://localhost"}},configurable:true});
const request = (adapter:ReturnType<typeof createDemoAdapter>, message:string, id=crypto.randomUUID()) => adapter.fetch("/api/teaching/turns/stream", {method:"POST",body:JSON.stringify({message,mode:"review_derivations",client_request_id:id})});
function result(stream:string) {const block=stream.split("\n\n").find(s=>s.startsWith("event: workflow.completed"));assert.ok(block);return parseTeachingTurnResult(JSON.parse(block.split("data: ")[1]));}
test("offline loop validates contracts, rejects skips and arbitrary answers, restores and isolates sessions",async()=>{
 values.clear();const a=createDemoAdapter();assert.equal((await request(a,samples[5])).status,422);
 const id=crypto.randomUUID();const first=await (await request(a,samples[0],id)).text();assert.equal(result(first).learning_native?.phase,"commitment_required");assert.equal(await(await request(a,samples[1],id)).text(),first);
 assert.equal(result(await(await request(a,samples[0])).text()).learning_native?.phase,"commitment_required");
 for(let i=1;i<5;i++)result(await(await request(a,samples[i])).text());
 assert.equal((await request(a,"T=0，随宽度增加而上升")).status,422);
 const restored=createDemoAdapter();assert.equal(restored.next(),samples[5]);
 const last=result(await(await request(restored,samples[5])).text());assert.equal(last.learning_native?.phase,"complete");
 const previous=last.conversation_id;restored.reset();const fresh=createDemoAdapter();const newResult=result(await(await request(fresh,samples[0])).text());assert.notEqual(newResult.conversation_id,previous);
});
