import { FormEvent, useEffect, useState } from 'react'
import { Bot, Code2, Container, Globe2, LockKeyhole, Pencil, PlugZap, Plus, Search, Sparkles, Trash2, Users } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { portsToSchema, schemaToPorts, type PortDefinition, type PortType } from '../lib/contracts'
import { translateStatus, translateVisibility, useI18n } from '../i18n'
import type { Agent, AgentKind, McpServer, McpTool, Provider, ProviderModel, Visibility } from '../types'

type CrewMember = { role:string; goal:string; backstory:string; allow_delegation:boolean; max_iter:number }
type CrewTask = { name:string; description:string; expected_output:string; agent_role:string }
type Translate = ReturnType<typeof useI18n>['t']
const defaultCrewMember=(t:Translate):CrewMember=>({role:t('agents.defaultRole'),goal:t('agents.defaultGoal'),backstory:t('agents.defaultBackstory'),allow_delegation:false,max_iter:20})
const defaultCrewTask=(t:Translate):CrewTask=>({name:t('agents.defaultTaskName'),description:t('agents.defaultTaskDescription'),expected_output:t('agents.defaultExpectedOutput'),agent_role:t('agents.defaultRole')})

export function AgentsPage({onTest}:{onTest?:(agent:Agent)=>void}) {
  const {t}=useI18n()
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
  const [outputs, setOutputs] = useState<PortDefinition[]>([{name:'result',type:'string',required:false,description:t('agents.resultDescription')}])
  const [crewProcess,setCrewProcess]=useState<'sequential'|'hierarchical'>('sequential')
  const [crewMembers,setCrewMembers]=useState<CrewMember[]>([defaultCrewMember(t)])
  const [crewTasks,setCrewTasks]=useState<CrewTask[]>([defaultCrewTask(t)])
  useEffect(() => { api<Agent[]>('/agents').then(setAgents).catch(() => setAgents([])) }, [])
  useEffect(() => { api<Provider[]>('/providers').then(setProviders).catch(() => setProviders([])) }, [])
  useEffect(() => { api<McpServer[]>('/mcp-servers').then(setMcpServers).catch(() => setMcpServers([])) }, [])
  useEffect(() => { if (providerId) api<ProviderModel[]>(`/providers/${providerId}/models`).then(setModels); else setModels([]) }, [providerId])

  function openNew(){setEditing(null);setKind('ai');setProviderId('');setModelId('');setMcpServerId('');setMcpToolName('');setInputs([]);setOutputs([{name:'result',type:'string',required:false,description:t('agents.resultDescription')}]);setCrewProcess('sequential');setCrewMembers([defaultCrewMember(t)]);setCrewTasks([defaultCrewTask(t)]);setError('');setCreating(true)}
  function openEdit(agent:Agent){
    const config=agent.draft_config
    setEditing(agent);setKind(agent.kind);setProviderId(agent.provider_id??'');setModelId(agent.model_catalog_id??'');setMcpServerId(agent.mcp_server_id??'');setMcpToolName(agent.mcp_tool_name??'');setInputs(schemaToPorts(agent.input_schema));setOutputs(schemaToPorts(agent.output_schema))
    setCrewProcess(config.process==='hierarchical'?'hierarchical':'sequential')
    setCrewMembers(Array.isArray(config.members)&&config.members.length?config.members as CrewMember[]:[defaultCrewMember(t)])
    setCrewTasks(Array.isArray(config.tasks)&&config.tasks.length?config.tasks as CrewTask[]:[defaultCrewTask(t)])
    setError('');setCreating(true)
  }
  function selectMcpTool(toolName:string){setMcpToolName(toolName);const server=mcpServers.find(item=>item.id===mcpServerId);const tool=server?.tools_snapshot.find(item=>item.name===toolName);if(!tool)return;setInputs(schemaToPorts(tool.inputSchema??{}));setOutputs(tool.outputSchema?schemaToPorts(tool.outputSchema):[{name:'result',type:'json',required:false,description:t('agents.completeMcpResult')}])}
  async function remove(agent:Agent){
    try{await api(`/agents/${agent.id}`,{method:'DELETE'});setAgents(current=>current.filter(item=>item.id!==agent.id));setError('');toast(t('agents.deleted',{name:agent.name}),'success',{kind:'agent.deleted',resource_type:'agent',resource_id:agent.id})}
    catch(reason){const message=reason instanceof Error?reason.message:t('agents.deleteFailed');setError(message);toast(message,'error',{kind:'agent.delete_failed',resource_type:'agent',resource_id:agent.id})}
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('agents.saveFailed')) }
  }

  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">{t('agents.eyebrow',{count:agents.length.toString().padStart(2,'0')})}</p><h1>{t('agents.title')}</h1><p>{t('agents.description')}</p></div><button className="button primary" onClick={openNew}><Plus size={16}/>{t('agents.new')}</button></header>
    {error&&!creating&&<div className="form-error page-error">{error}</div>}
    <div className="toolbar"><div className="search"><Search size={16}/><input placeholder={`${t('common.actions.search')}…`}/></div><button className="chip active">{t('agents.all')}</button><button className="chip">AI</button><button className="chip">CrewAI</button><button className="chip">Script</button><button className="chip">MCP</button></div>
    <div className="agent-grid">
      {agents.map(agent => <article className="agent-card" key={agent.id}><div className={`agent-avatar ${agent.kind}`}><span>{agent.kind === 'ai' ? <Bot size={20}/> : agent.kind==='crewai'?<Users size={20}/>:agent.kind==='mcp'?<PlugZap size={20}/>:<Code2 size={20}/>}</span><i/></div><div className="card-top"><span className={`resource-tag ${agent.execution_requirement}`}>{agent.execution_requirement.toUpperCase()}</span><span className="type-tag">{agent.kind.toUpperCase()}</span><span title={translateVisibility(agent.visibility)}>{agent.visibility === 'public' ? <Globe2 size={14}/> : agent.visibility === 'groups' ? <Users size={14}/> : <LockKeyhole size={14}/>}</span></div><h3>{agent.name}</h3><p>{agent.description || agent.purpose || t('agents.noDescription')}</p><div className="card-meta"><span>{agent.kind==='mcp'?agent.mcp_tool_name:agent.kind==='crewai'?t('agents.membersRuntime',{count:Array.isArray(agent.draft_config.members)?agent.draft_config.members.length:0,process:String(agent.draft_config.process??'sequential')}):String(agent.draft_config.deployment_mode ?? t('agents.runtimeUndefined'))}</span><span>DRAFT</span></div><div className="agent-actions"><button className="button ghost" onClick={()=>openEdit(agent)}><Pencil size={14}/>{t('common.actions.edit')}</button><button className="button ghost" onClick={()=>onTest?.(agent)}><Sparkles size={14}/>{t('agents.test')}</button><button className="icon-button danger" title={t('common.actions.delete')} onClick={()=>remove(agent)}><Trash2 size={14}/></button></div></article>)}
      {!agents.length && <div className="empty-state"><Sparkles size={24}/><h3>{t('agents.emptyTitle')}</h3><p>{t('agents.emptyDescription')}</p><button className="button primary" onClick={openNew}>{t('agents.new')}</button></div>}
    </div>
    {creating && <div className="modal-backdrop" onMouseDown={() => setCreating(false)}><form key={editing?.id??'new'} className="modal agent-modal" onSubmit={create} onMouseDown={e => e.stopPropagation()}><p className="eyebrow">{editing?t('agents.editEyebrow'):t('agents.newEyebrow')}</p><h2>{editing?t('agents.editTitle'):t('agents.createTitle')}</h2><div className="form-grid"><label>{t('common.fields.name')}<input name="name" required defaultValue={editing?.name??''} placeholder="Document Analyzer"/></label><label>{t('agents.kind')}<select name="kind" value={kind} onChange={e => setKind(e.target.value as AgentKind)}><option value="ai">AI agent</option><option value="crewai">{t('agents.crew.title')}</option><option value="script">Script agent</option><option value="mcp">MCP agent</option></select></label><label>{t('agents.requirement')}<select name="executionRequirement" defaultValue={editing?.execution_requirement??'cpu'}><option value="cpu">{t('agents.cpuEnough')}</option><option value="gpu">{t('agents.gpuRequired')}</option></select></label><label className="span-2">{t('agents.shortDescription')}<input name="description" defaultValue={editing?.description??''} placeholder={t('agents.shortDescriptionPlaceholder')}/></label><label className="span-2">{t('agents.purpose')}<textarea name="purpose" defaultValue={editing?.purpose??''} placeholder={t('agents.purposePlaceholder')}/></label>
      {kind === 'ai'||kind==='crewai' ? <><label>{t('agents.provider')}<select name="providerId" value={providerId} onChange={e => {setProviderId(e.target.value);setModelId('')}} required><option value="">{t('agents.chooseProvider')}</option>{providers.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label><label>{t('agents.model')}<select name="modelId" required disabled={!models.length} value={modelId} onChange={e=>setModelId(e.target.value)}><option value="">{providerId?t('agents.chooseModel'):t('agents.chooseProviderFirst')}</option>{models.map(model => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>{kind==='ai'?<label className="span-2">{t('agents.deployment')}<select name="deploymentMode" defaultValue={String(editing?.draft_config.deployment_mode??'managed-ai')}><option value="managed-ai">{t('agents.managedAi')}</option><option value="custom-image">{t('agents.customAi')}</option></select></label>:<div className="span-2"><CrewEditor process={crewProcess} onProcess={setCrewProcess} members={crewMembers} onMembers={setCrewMembers} tasks={crewTasks} onTasks={setCrewTasks}/></div>}</> : kind==='mcp'?<><label>{t('agents.mcpServer')}<select name="mcpServerId" required value={mcpServerId} onChange={event=>{setMcpServerId(event.target.value);setMcpToolName('')}}><option value="">{t('agents.chooseMcpServer')}</option>{mcpServers.filter(server=>server.status!=='disabled').map(server=><option value={server.id} key={server.id}>{server.name} · {translateStatus(server.status)}</option>)}</select></label><label>{t('agents.mcpTool')}{(mcpServers.find(server=>server.id===mcpServerId)?.tools_snapshot.length??0)>0?<select name="mcpToolName" required value={mcpToolName} onChange={event=>selectMcpTool(event.target.value)}><option value="">{t('agents.chooseMcpTool')}</option>{mcpServers.find(server=>server.id===mcpServerId)?.tools_snapshot.map((tool:McpTool)=><option value={tool.name} key={tool.name}>{tool.title??tool.name}</option>)}</select>:<input name="mcpToolName" required value={mcpToolName} onChange={event=>setMcpToolName(event.target.value)} placeholder="case-sensitive tool name"/>}</label><div className="connection-hint span-2"><PlugZap size={14}/><p>{t('agents.mcpContractHint')}</p></div></>:<><label>{t('agents.deployment')}<select name="deploymentMode" defaultValue={String(editing?.draft_config.deployment_mode??'managed-script')}><option value="managed-script">{t('agents.processDeployment')}</option><option value="custom-image">{t('agents.podmanDeployment')}</option></select></label><label>{t('agents.language')}<select name="language" defaultValue={String(editing?.draft_config.language??'python')}><option value="python">Python</option><option value="node">Node.js</option><option value="bash">Bash</option></select></label><label className="span-2">{t('agents.imagePodman')}<input name="image" defaultValue={String(editing?.draft_config.image??'')} placeholder="registry.example.com/my-agent:1.0"/></label><label className="span-2">{t('agents.processCode')}<textarea className="code-input" name="code" defaultValue={String(editing?.draft_config.code??'')}/><small>{t('agents.processCodeHint')}</small></label></>}
      <label>{t('common.fields.visibility')}<select name="visibility" defaultValue={editing?.visibility??'private'}><option value="private">{t('visibility.private')}</option><option value="public">{t('visibility.public')}</option><option value="groups">{t('visibility.groups')}</option></select></label></div>
      <div className="contract-editors"><PortEditor title={t('agents.inputs')} hint={t('agents.inputsHint')} ports={inputs} onChange={setInputs}/><PortEditor title={t('agents.outputs')} hint={t('agents.outputsHint')} ports={outputs} onChange={setOutputs}/></div>
      {(kind === 'ai'||kind==='crewai') && !providers.length && <div className="connection-hint"><Container size={14}/><p>{t('agents.noProviderHint')}</p></div>}{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={() => setCreating(false)}>{t('common.actions.cancel')}</button><button className="button primary">{editing?t('agents.saveChanges'):t('agents.saveDraft')}</button></div></form></div>}
  </div>
}

function CrewEditor({process,onProcess,members,onMembers,tasks,onTasks}:{process:'sequential'|'hierarchical';onProcess:(value:'sequential'|'hierarchical')=>void;members:CrewMember[];onMembers:(value:CrewMember[])=>void;tasks:CrewTask[];onTasks:(value:CrewTask[])=>void}) {
  const {t}=useI18n()
  function patchMember(index:number,value:Partial<CrewMember>){
    const previous=members[index].role
    const next=members.map((member,i)=>i===index?{...member,...value}:member)
    onMembers(next)
    if(value.role!==undefined&&value.role!==previous)onTasks(tasks.map(task=>task.agent_role===previous?{...task,agent_role:value.role!}:task))
  }
  function patchTask(index:number,value:Partial<CrewTask>){onTasks(tasks.map((task,i)=>i===index?{...task,...value}:task))}
  return <section className="crew-editor"><div className="crew-heading"><div><h3>{t('agents.crew.title')}</h3><p>{t('agents.crew.description')}</p></div><label>{t('agents.crew.process')}<select value={process} onChange={event=>onProcess(event.target.value as typeof process)}><option value="sequential">{t('agents.crew.sequential')}</option><option value="hierarchical">{t('agents.crew.hierarchical')}</option></select></label></div>
    <div className="crew-section"><div className="crew-section-head"><strong>{t('agents.crew.members',{count:members.length}).toUpperCase()}</strong><button type="button" className="button ghost" onClick={()=>onMembers([...members,{...defaultCrewMember(t),role:t('agents.specialist',{number:members.length+1})}])}><Plus size={13}/>{t('agents.crew.member')}</button></div>{members.map((member,index)=><article className="crew-item" key={index}><div className="crew-item-title"><b>{index+1}. {member.role||t('agents.crew.newMember')}</b><button type="button" className="icon-button danger" disabled={members.length===1} onClick={()=>{const remaining=members.filter((_,i)=>i!==index);onMembers(remaining);onTasks(tasks.map(task=>task.agent_role===member.role?{...task,agent_role:remaining[0]?.role??''}:task))}}><Trash2 size={13}/></button></div><div className="crew-fields"><label>{t('common.fields.role')}<input required value={member.role} onChange={event=>patchMember(index,{role:event.target.value})}/></label><label>{t('agents.crew.goal')}<input required value={member.goal} onChange={event=>patchMember(index,{goal:event.target.value})}/></label><label className="wide">{t('agents.crew.backstory')}<textarea required value={member.backstory} onChange={event=>patchMember(index,{backstory:event.target.value})}/></label><label>{t('agents.crew.maxIterations')}<input type="number" min={1} max={100} value={member.max_iter} onChange={event=>patchMember(index,{max_iter:Number(event.target.value)})}/></label><label className="crew-check"><input type="checkbox" checked={member.allow_delegation} onChange={event=>patchMember(index,{allow_delegation:event.target.checked})}/>{t('agents.crew.canDelegate')}</label></div></article>)}</div>
    <div className="crew-section"><div className="crew-section-head"><strong>{t('agents.crew.tasks',{count:tasks.length}).toUpperCase()}</strong><button type="button" className="button ghost" onClick={()=>onTasks([...tasks,{...defaultCrewTask(t),name:`${t('agents.crew.task')} ${tasks.length+1}`,agent_role:members[0]?.role??''}])}><Plus size={13}/>{t('agents.crew.task')}</button></div>{tasks.map((task,index)=><article className="crew-item" key={index}><div className="crew-item-title"><b>{index+1}. {task.name||t('agents.crew.newTask')}</b><button type="button" className="icon-button danger" disabled={tasks.length===1} onClick={()=>onTasks(tasks.filter((_,i)=>i!==index))}><Trash2 size={13}/></button></div><div className="crew-fields"><label>{t('common.fields.name')}<input required value={task.name} onChange={event=>patchTask(index,{name:event.target.value})}/></label><label>{t('agents.crew.executedBy')}<select required value={task.agent_role} onChange={event=>patchTask(index,{agent_role:event.target.value})}>{members.map(member=><option value={member.role} key={member.role}>{member.role}</option>)}</select></label><label className="wide">{t('agents.crew.assignment')}<textarea required value={task.description} onChange={event=>patchTask(index,{description:event.target.value})}/><small>{t('agents.crew.assignmentHint',{example:'{tema}'})}</small></label><label className="wide">{t('agents.crew.expected')}<textarea required value={task.expected_output} onChange={event=>patchTask(index,{expected_output:event.target.value})}/></label></div></article>)}</div>
    <div className="connection-hint"><Users size={14}/><p>{t('agents.crew.outputHint')}</p></div>
  </section>
}

const portTypes: Array<{value:PortType;label:string}> = [
  {value:'string',label:'String'}, {value:'json',label:'JSON'}, {value:'number',label:'Number'},
  {value:'boolean',label:'Boolean'}, {value:'file',label:'File'}, {value:'image',label:'Image'}, {value:'any',label:'Any'},
]

function PortEditor({title,hint,ports,onChange}:{title:string;hint:string;ports:PortDefinition[];onChange:(ports:PortDefinition[])=>void}) {
  const {t}=useI18n()
  function patch(index:number, value:Partial<PortDefinition>){onChange(ports.map((port,i)=>i===index?{...port,...value}:port))}
  function add(){onChange([...ports,{name:`value_${ports.length+1}`,type:'string',required:true,description:''}])}
  return <section className="port-editor"><div className="port-editor-head"><div><h3>{title}</h3><p>{hint}</p></div><button type="button" className="button ghost" onClick={add}><Plus size={13}/>{t('agents.portAdd')}</button></div>
    <div className="port-table"><div className="port-row port-head"><span>{t('agents.portName').toUpperCase()}</span><span>{t('agents.portType').toUpperCase()}</span><span>{t('agents.portRequired').toUpperCase()}</span><span/></div>{ports.map((port,index)=><div className="port-row" key={index}><input value={port.name} onChange={event=>patch(index,{name:event.target.value.replace(/[^a-zA-Z0-9_.-]/g,'_')})} placeholder="input_name" required/><select value={port.type} onChange={event=>patch(index,{type:event.target.value as PortType})}>{portTypes.map(type=><option value={type.value} key={type.value}>{type.label}</option>)}</select><label className="port-required"><input type="checkbox" checked={port.required} onChange={event=>patch(index,{required:event.target.checked})}/><span/></label><button type="button" className="icon-button danger" onClick={()=>onChange(ports.filter((_,i)=>i!==index))}><Trash2 size={13}/></button></div>)}</div>
    {!ports.length&&<div className="port-empty">{t('agents.noPorts',{direction:title.toLowerCase()})}</div>}
  </section>
}
