import { FormEvent, useEffect, useState } from 'react'
import { Bot, Code2, Container, Globe2, LockKeyhole, Pencil, PlugZap, Plus, Search, Sparkles, Trash2, Users } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { portsToSchema, schemaToPorts, type PortDefinition, type PortType } from '../lib/contracts'
import type { Agent, AgentKind, McpServer, McpTool, Provider, ProviderModel, Visibility } from '../types'

type CrewMember = { role:string; goal:string; backstory:string; allow_delegation:boolean; max_iter:number }
type CrewTask = { name:string; description:string; expected_output:string; agent_role:string }
const defaultCrewMember: CrewMember = {role:'Analytik',goal:'Spracovať zverenú časť úlohy',backstory:'Skúsený špecialista, ktorý pracuje presne a odovzdáva overiteľný výsledok.',allow_delegation:false,max_iter:20}
const defaultCrewTask: CrewTask = {name:'Spracovanie',description:'Spracuj pomenované vstupy pipeline a splň cieľ tímu.',expected_output:'Presný výsledok podľa výstupného kontraktu.',agent_role:'Analytik'}

export function AgentsPage({onTest}:{onTest?:(agent:Agent)=>void}) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Agent|null>(null)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState<Provider[]>([])
  const [models, setModels] = useState<ProviderModel[]>([])
  const [mcpServers,setMcpServers]=useState<McpServer[]>([])
  const [mcpServerId,setMcpServerId]=useState('')
  const [mcpToolName,setMcpToolName]=useState('')
  const [kind, setKind] = useState<AgentKind>('ai')
  const [providerId, setProviderId] = useState('')
  const [modelId, setModelId] = useState('')
  const [inputs, setInputs] = useState<PortDefinition[]>([])
  const [outputs, setOutputs] = useState<PortDefinition[]>([{name:'result',type:'string',required:false,description:'Výsledok agenta'}])
  const [crewProcess,setCrewProcess]=useState<'sequential'|'hierarchical'>('sequential')
  const [crewMembers,setCrewMembers]=useState<CrewMember[]>([{...defaultCrewMember}])
  const [crewTasks,setCrewTasks]=useState<CrewTask[]>([{...defaultCrewTask}])
  useEffect(() => { api<Agent[]>('/agents').then(setAgents).catch(() => setAgents([])) }, [])
  useEffect(() => { api<Provider[]>('/providers').then(setProviders).catch(() => setProviders([])) }, [])
  useEffect(() => { api<McpServer[]>('/mcp-servers').then(setMcpServers).catch(() => setMcpServers([])) }, [])
  useEffect(() => { if (providerId) api<ProviderModel[]>(`/providers/${providerId}/models`).then(setModels); else setModels([]) }, [providerId])

  function openNew(){setEditing(null);setKind('ai');setProviderId('');setModelId('');setMcpServerId('');setMcpToolName('');setInputs([]);setOutputs([{name:'result',type:'string',required:false,description:'Výsledok agenta'}]);setCrewProcess('sequential');setCrewMembers([{...defaultCrewMember}]);setCrewTasks([{...defaultCrewTask}]);setError('');setCreating(true)}
  function openEdit(agent:Agent){
    const config=agent.draft_config
    setEditing(agent);setKind(agent.kind);setProviderId(agent.provider_id??'');setModelId(agent.model_catalog_id??'');setMcpServerId(agent.mcp_server_id??'');setMcpToolName(agent.mcp_tool_name??'');setInputs(schemaToPorts(agent.input_schema));setOutputs(schemaToPorts(agent.output_schema))
    setCrewProcess(config.process==='hierarchical'?'hierarchical':'sequential')
    setCrewMembers(Array.isArray(config.members)&&config.members.length?config.members as CrewMember[]:[{...defaultCrewMember}])
    setCrewTasks(Array.isArray(config.tasks)&&config.tasks.length?config.tasks as CrewTask[]:[{...defaultCrewTask}])
    setError('');setCreating(true)
  }
  function selectMcpTool(toolName:string){setMcpToolName(toolName);const server=mcpServers.find(item=>item.id===mcpServerId);const tool=server?.tools_snapshot.find(item=>item.name===toolName);if(!tool)return;setInputs(schemaToPorts(tool.inputSchema??{}));setOutputs(tool.outputSchema?schemaToPorts(tool.outputSchema):[{name:'result',type:'json',required:false,description:'Kompletný MCP tool result'}])}
  async function remove(agent:Agent){
    try{await api(`/agents/${agent.id}`,{method:'DELETE'});setAgents(current=>current.filter(item=>item.id!==agent.id));setError('');toast(`Agent „${agent.name}“ bol vymazaný.`,'success',{kind:'agent.deleted',resource_type:'agent',resource_id:agent.id})}
    catch(reason){const message=reason instanceof Error?reason.message:'Agenta sa nepodarilo vymazať';setError(message);toast(message,'error',{kind:'agent.delete_failed',resource_type:'agent',resource_id:agent.id})}
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name'))
    try {
      const agent = await api<Agent>(editing?`/agents/${editing.id}`:'/agents', { method: editing?'PUT':'POST', body: JSON.stringify({
        name, slug: editing?.slug??name.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
        description: data.get('description'), purpose: data.get('purpose'), kind: data.get('kind') as AgentKind,
        execution_requirement: data.get('executionRequirement'),
        visibility: data.get('visibility') as Visibility,
        provider_id: data.get('providerId') || null, model_catalog_id: data.get('modelId') || null,
        mcp_server_id: data.get('mcpServerId') || null, mcp_tool_name: data.get('mcpToolName') || null,
        draft_config: kind==='crewai'
          ? {deployment_mode:'crewai',process:crewProcess,members:crewMembers,tasks:crewTasks,memory:false,cache:false,timeout_seconds:900}
          : { deployment_mode: kind==='mcp'?'mcp':data.get('deploymentMode'), language: data.get('language') || null, image: data.get('image') || null, code: data.get('code') || null, timeout_seconds: 300 },
        input_schema: portsToSchema(inputs), output_schema: portsToSchema(outputs),
      }) })
      setAgents(current => editing?current.map(item=>item.id===agent.id?agent:item):[agent, ...current]); setCreating(false);setEditing(null);setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Agenta sa nepodarilo uložiť') }
  }

  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">REGISTRY / {agents.length.toString().padStart(2, '0')}</p><h1>Agenti</h1><p>Navrhuj, verziuj a spravuj pracovné jednotky.</p></div><button className="button primary" onClick={openNew}><Plus size={16} />Nový agent</button></header>
    {error&&!creating&&<div className="form-error page-error">{error}</div>}
    <div className="toolbar"><div className="search"><Search size={16} /><input placeholder="Hľadať agenta…" /></div><button className="chip active">Všetci</button><button className="chip">AI</button><button className="chip">CrewAI</button><button className="chip">Script</button><button className="chip">MCP</button></div>
    <div className="agent-grid">
      {agents.map(agent => <article className="agent-card" key={agent.id}><div className={`agent-avatar ${agent.kind}`}><span>{agent.kind === 'ai' ? <Bot size={20} /> : agent.kind==='crewai'?<Users size={20}/>:agent.kind==='mcp'?<PlugZap size={20}/>:<Code2 size={20} />}</span><i /></div><div className="card-top"><span className={`resource-tag ${agent.execution_requirement}`}>{agent.execution_requirement.toUpperCase()}</span><span className="type-tag">{agent.kind.toUpperCase()}</span><span title={agent.visibility}>{agent.visibility === 'public' ? <Globe2 size={14} /> : agent.visibility === 'groups' ? <Users size={14} /> : <LockKeyhole size={14} />}</span></div><h3>{agent.name}</h3><p>{agent.description || agent.purpose || 'Bez popisu'}</p><div className="card-meta"><span>{agent.kind==='mcp'?agent.mcp_tool_name:agent.kind==='crewai'?`${Array.isArray(agent.draft_config.members)?agent.draft_config.members.length:0} členov · ${String(agent.draft_config.process??'sequential')}`:String(agent.draft_config.deployment_mode ?? 'Runtime neurčený')}</span><span>DRAFT</span></div><div className="agent-actions"><button className="button ghost" onClick={()=>openEdit(agent)}><Pencil size={14}/>Editovať</button><button className="button ghost" onClick={()=>onTest?.(agent)}><Sparkles size={14}/>Testovať</button><button className="icon-button danger" title="Vymazať" onClick={()=>remove(agent)}><Trash2 size={14}/></button></div></article>)}
      {!agents.length && <div className="empty-state"><Sparkles size={24} /><h3>Zatiaľ tu nie sú agenti</h3><p>Vytvor prvého AI alebo script agenta.</p><button className="button primary" onClick={openNew}>Vytvoriť agenta</button></div>}
    </div>
    {creating && <div className="modal-backdrop" onMouseDown={() => setCreating(false)}><form key={editing?.id??'new'} className="modal agent-modal" onSubmit={create} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">{editing?'EDIT AGENT':'NEW AGENT'}</p><h2>{editing?'Upraviť agenta':'Vytvoriť agenta'}</h2><div className="form-grid"><label>Meno<input name="name" required defaultValue={editing?.name??''} placeholder="Document Analyzer" /></label><label>Typ<select name="kind" value={kind} onChange={e => setKind(e.target.value as AgentKind)}><option value="ai">AI agent</option><option value="crewai">CrewAI tím</option><option value="script">Script agent</option><option value="mcp">MCP agent</option></select></label><label>Výpočtová požiadavka<select name="executionRequirement" defaultValue={editing?.execution_requirement??'cpu'}><option value="cpu">CPU postačuje</option><option value="gpu">Vyžaduje GPU</option></select></label><label className="span-2">Krátky popis<input name="description" defaultValue={editing?.description??''} placeholder="Čo agent robí — bez väzby na konkrétnu doménu" /></label><label className="span-2">Určenie<textarea name="purpose" defaultValue={editing?.purpose??''} placeholder="Podrobná zodpovednosť a hranice agenta…" /></label>
      {kind === 'ai'||kind==='crewai' ? <><label>Provider<select name="providerId" value={providerId} onChange={e => {setProviderId(e.target.value);setModelId('')}} required><option value="">Vyber pripojený provider</option>{providers.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label><label>Model<select name="modelId" required disabled={!models.length} value={modelId} onChange={e=>setModelId(e.target.value)}><option value="">{providerId ? 'Vyber model' : 'Najprv vyber provider'}</option>{models.map(model => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>{kind==='ai'?<label className="span-2">Deployment<select name="deploymentMode" defaultValue={String(editing?.draft_config.deployment_mode??'managed-ai')}><option value="managed-ai">Managed AI runtime — worker volá provider</option><option value="custom-image">Custom OCI image — vlastný agent runtime</option></select></label>:<div className="span-2"><CrewEditor process={crewProcess} onProcess={setCrewProcess} members={crewMembers} onMembers={setCrewMembers} tasks={crewTasks} onTasks={setCrewTasks}/></div>}</> : kind==='mcp'?<><label>MCP server<select name="mcpServerId" required value={mcpServerId} onChange={event=>{setMcpServerId(event.target.value);setMcpToolName('')}}><option value="">Vyber server</option>{mcpServers.filter(server=>server.status!=='disabled').map(server=><option value={server.id} key={server.id}>{server.name} · {server.status}</option>)}</select></label><label>Tool{(mcpServers.find(server=>server.id===mcpServerId)?.tools_snapshot.length??0)>0?<select name="mcpToolName" required value={mcpToolName} onChange={event=>selectMcpTool(event.target.value)}><option value="">Vyber synchronizovaný tool</option>{mcpServers.find(server=>server.id===mcpServerId)?.tools_snapshot.map((tool:McpTool)=><option value={tool.name} key={tool.name}>{tool.title??tool.name}</option>)}</select>:<input name="mcpToolName" required value={mcpToolName} onChange={event=>setMcpToolName(event.target.value)} placeholder="case-sensitive tool name"/>}</label><div className="connection-hint span-2"><PlugZap size={14}/><p>Argumenty toolu sú pomenované vstupy agenta. structuredContent sa zachová ako pomenované výstupy pre ďalšie nodes.</p></div></>:<><label>Deployment<select name="deploymentMode" defaultValue={String(editing?.draft_config.deployment_mode??'managed-script')}><option value="managed-script">Process — spustiť priamo na Linux workerovi</option><option value="custom-image">Podman — vlastný OCI image</option></select></label><label>Jazyk<select name="language" defaultValue={String(editing?.draft_config.language??'python')}><option value="python">Python</option><option value="node">Node.js</option><option value="bash">Bash</option></select></label><label className="span-2">OCI image (iba Podman)<input name="image" defaultValue={String(editing?.draft_config.image??'')} placeholder="registry.example.com/my-agent:1.0"/></label><label className="span-2">Kód procesu<textarea className="code-input" name="code" defaultValue={String(editing?.draft_config.code??'')}/><small>Stačí vypísať výsledok na stdout, napr. <code>ls</code>. Worker ho automaticky zabalí podľa výstupného portu. AF_OUTPUT_PATH je iba voliteľný pre explicitný JSON.</small></label></>}
      <label>Viditeľnosť<select name="visibility" defaultValue={editing?.visibility??'private'}><option value="private">Private</option><option value="public">Public</option><option value="groups">Groups</option></select></label></div>
      <div className="contract-editors"><PortEditor title="Očakávané vstupy" hint="Hodnoty, ktoré musí dodať pipeline alebo predchádzajúci agent." ports={inputs} onChange={setInputs}/><PortEditor title="Štruktúra výstupu" hint="Pomenované výsledky dostupné ďalším krokom." ports={outputs} onChange={setOutputs}/></div>
      {(kind === 'ai'||kind==='crewai') && !providers.length && <div className="connection-hint"><Container size={14}/><p>Najprv v menu <strong>Providery a modely</strong> pripoj Ollama alebo OpenAI-compatible API. Žiadne modely nie sú prednastavené.</p></div>}{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={() => setCreating(false)}>Zrušiť</button><button className="button primary">{editing?'Uložiť zmeny':'Uložiť draft'}</button></div></form></div>}
  </div>
}

function CrewEditor({process,onProcess,members,onMembers,tasks,onTasks}:{process:'sequential'|'hierarchical';onProcess:(value:'sequential'|'hierarchical')=>void;members:CrewMember[];onMembers:(value:CrewMember[])=>void;tasks:CrewTask[];onTasks:(value:CrewTask[])=>void}) {
  function patchMember(index:number,value:Partial<CrewMember>){
    const previous=members[index].role
    const next=members.map((member,i)=>i===index?{...member,...value}:member)
    onMembers(next)
    if(value.role!==undefined&&value.role!==previous)onTasks(tasks.map(task=>task.agent_role===previous?{...task,agent_role:value.role!}:task))
  }
  function patchTask(index:number,value:Partial<CrewTask>){onTasks(tasks.map((task,i)=>i===index?{...task,...value}:task))}
  return <section className="crew-editor"><div className="crew-heading"><div><h3>CrewAI tím</h3><p>LangGraph riadi node; CrewAI vykoná tento izolovaný tím.</p></div><label>Proces<select value={process} onChange={event=>onProcess(event.target.value as typeof process)}><option value="sequential">Sekvenčný</option><option value="hierarchical">Hierarchický</option></select></label></div>
    <div className="crew-section"><div className="crew-section-head"><strong>ČLENOVIA / {members.length}</strong><button type="button" className="button ghost" onClick={()=>onMembers([...members,{...defaultCrewMember,role:`Špecialista ${members.length+1}`}])}><Plus size={13}/>Člen</button></div>{members.map((member,index)=><article className="crew-item" key={index}><div className="crew-item-title"><b>{index+1}. {member.role||'Nový člen'}</b><button type="button" className="icon-button danger" disabled={members.length===1} onClick={()=>{const remaining=members.filter((_,i)=>i!==index);onMembers(remaining);onTasks(tasks.map(task=>task.agent_role===member.role?{...task,agent_role:remaining[0]?.role??''}:task))}}><Trash2 size={13}/></button></div><div className="crew-fields"><label>Rola<input required value={member.role} onChange={event=>patchMember(index,{role:event.target.value})}/></label><label>Cieľ<input required value={member.goal} onChange={event=>patchMember(index,{goal:event.target.value})}/></label><label className="wide">Backstory<textarea required value={member.backstory} onChange={event=>patchMember(index,{backstory:event.target.value})}/></label><label>Max. iterácií<input type="number" min={1} max={100} value={member.max_iter} onChange={event=>patchMember(index,{max_iter:Number(event.target.value)})}/></label><label className="crew-check"><input type="checkbox" checked={member.allow_delegation} onChange={event=>patchMember(index,{allow_delegation:event.target.checked})}/>Môže delegovať</label></div></article>)}</div>
    <div className="crew-section"><div className="crew-section-head"><strong>ÚLOHY / {tasks.length}</strong><button type="button" className="button ghost" onClick={()=>onTasks([...tasks,{...defaultCrewTask,name:`Úloha ${tasks.length+1}`,agent_role:members[0]?.role??''}])}><Plus size={13}/>Úloha</button></div>{tasks.map((task,index)=><article className="crew-item" key={index}><div className="crew-item-title"><b>{index+1}. {task.name||'Nová úloha'}</b><button type="button" className="icon-button danger" disabled={tasks.length===1} onClick={()=>onTasks(tasks.filter((_,i)=>i!==index))}><Trash2 size={13}/></button></div><div className="crew-fields"><label>Názov<input required value={task.name} onChange={event=>patchTask(index,{name:event.target.value})}/></label><label>Vykonáva<select required value={task.agent_role} onChange={event=>patchTask(index,{agent_role:event.target.value})}>{members.map(member=><option value={member.role} key={member.role}>{member.role}</option>)}</select></label><label className="wide">Zadanie<textarea required value={task.description} onChange={event=>patchTask(index,{description:event.target.value})}/><small>Pomenované vstupy môžeš vložiť ako <code>{'{tema}'}</code>.</small></label><label className="wide">Očakávaný výsledok<textarea required value={task.expected_output} onChange={event=>patchTask(index,{expected_output:event.target.value})}/></label></div></article>)}</div>
    <div className="connection-hint"><Users size={14}/><p>Posledná úloha musí vrátiť pomenované polia z výstupného kontraktu. Worker ich vynúti cez štruktúrovaný Pydantic výstup.</p></div>
  </section>
}

const portTypes: Array<{value:PortType;label:string}> = [
  {value:'string',label:'String'}, {value:'json',label:'JSON'}, {value:'number',label:'Number'},
  {value:'boolean',label:'Boolean'}, {value:'file',label:'File'}, {value:'image',label:'Image'}, {value:'any',label:'Any'},
]

function PortEditor({title,hint,ports,onChange}:{title:string;hint:string;ports:PortDefinition[];onChange:(ports:PortDefinition[])=>void}) {
  function patch(index:number, value:Partial<PortDefinition>){onChange(ports.map((port,i)=>i===index?{...port,...value}:port))}
  function add(){onChange([...ports,{name:`value_${ports.length+1}`,type:'string',required:true,description:''}])}
  return <section className="port-editor"><div className="port-editor-head"><div><h3>{title}</h3><p>{hint}</p></div><button type="button" className="button ghost" onClick={add}><Plus size={13}/>Pridať</button></div>
    <div className="port-table"><div className="port-row port-head"><span>NÁZOV</span><span>TYP</span><span>POVINNÝ</span><span/></div>{ports.map((port,index)=><div className="port-row" key={index}><input value={port.name} onChange={event=>patch(index,{name:event.target.value.replace(/[^a-zA-Z0-9_.-]/g,'_')})} placeholder="input_name" required/><select value={port.type} onChange={event=>patch(index,{type:event.target.value as PortType})}>{portTypes.map(type=><option value={type.value} key={type.value}>{type.label}</option>)}</select><label className="port-required"><input type="checkbox" checked={port.required} onChange={event=>patch(index,{required:event.target.checked})}/><span/></label><button type="button" className="icon-button danger" onClick={()=>onChange(ports.filter((_,i)=>i!==index))}><Trash2 size={13}/></button></div>)}</div>
    {!ports.length&&<div className="port-empty">Žiadne hodnoty — agent môže fungovať bez {title.toLowerCase()}.</div>}
  </section>
}
