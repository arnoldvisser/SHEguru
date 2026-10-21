// Model and rendering checks without a browser. Browser layout is checked separately.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
const node=key=>{if(!nodes.has(key))nodes.set(key,{content:'test-token',textContent:'',innerHTML:'',style:{},classList:{remove(){}},isConnected:true,close(){},showModal(){},focus(){}});return nodes.get(key)};
const context={document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},console,Intl,Date,crypto:require('node:crypto').webcrypto,structuredClone,setTimeout:()=>0,clearTimeout(){},window:{scrollTo(){}},confirm:()=>true,fetch:async()=>{throw Error('Unexpected network call')}};
vm.createContext(context);
let code=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
code=code.slice(0,code.lastIndexOf('\nload().then(render)'));
vm.runInContext(code,context);
(async()=>{
await vm.runInContext(`(async()=>{
state={schemaVersion:1,company:{name:'Test',industry:'',location:''},employees:[{id:'e1',name:'A <script>',job:'',payrollId:'',active:true}],appointments:[{id:'a1',role:'First aid',employee:'e1',due:offset(90),duties:'',legalBasis:''}],training:[],tasks:[]};revision=1;
if(alerts().length!==0)throw Error('Covered appointment raised an alert');
state.employees[0].active=false;
if(alerts().length!==1||alerts()[0].target!=='Appointments')throw Error('Departure did not generate an appointment gap');
state.employees[0].active=true;
if(alerts().length!==0)throw Error('Reactivation did not clear the gap');
state.training=[{id:'t1',employee:'e1',course:'First aid',provider:'',due:offset(-1),completed:false,completedOn:''}];
if(alerts().length!==1)throw Error('Overdue training missing');
state.training[0].completed=true;
if(alerts().length!==0)throw Error('Completed training still alerts');
state.employees[0].active=false;
state.training[0].completed=false;
if(alerts().filter(x=>x.target==='Training').length!==0)throw Error('Training for a former employee remains in current alerts');
api=async(path)=>path==='state'?{state,revision}:[];
for(const tab of tabs){page=tab;await render()}
page='People';await render();
if(!document.querySelector('#view').innerHTML.includes('A &lt;script&gt;'))throw Error('Employee name was not escaped');
if(!button('Cancel','close').includes('type="button"'))throw Error('Cancel can submit a form');
const before=JSON.stringify(state);api=async()=>{const e=new Error('Conflict');e.status=409;throw e};
if(await commit(s=>s.company.name='Unpersisted')!==false)throw Error('Conflict reported success');
if(JSON.stringify(state)!==before)throw Error('Failed save mutated the displayed state');
api=async(path,options)=>{const p=JSON.parse(options.body);return {state:p.state,revision:p.revision+1}};
if(!await commit(s=>s.company.name='Saved company'))throw Error('Valid save failed');
if(state.company.name!=='Saved company'||revision!==2)throw Error('Saved state was not applied');
console.log('Frontend checks passed: departure/reactivation, training alerts, inactive employees, nine screen renders, HTML escaping, non-submit action buttons, conflict safety, successful save.');
})()`,context);
})().catch(e=>{console.error(e);process.exitCode=1});
