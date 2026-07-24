import { useEffect, useMemo, useState } from 'react'
import { Activity, Check, FileJson, ListTree, Radio, RotateCcw, Square, TerminalSquare, Zap } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { PipelineRun, RunEvent } from '../types'
import { translateStatus, translateTrigger, useI18n } from '../i18n'

type RunPage = {items:PipelineRun[];total:number;page:number;page_size:number;pages:number}
type RunFilterOptions = {pipelines:string[];agents:string[]}
type StatusFilter = 'all'|'failed'|'succeeded'

export function RunsPage(){
  const {t,dateTime,time}=useI18n()
  const [runs,setRuns]=useState<PipelineRun[]>([])
  const [total,setTotal]=useState(0)
  const [page,setPage]=useState(1)
  const [pages,setPages]=useState(1)
  const [statusFilter,setStatusFilter]=useState<StatusFilter>('all')
  const [pipelineFilter,setPipelineFilter]=useState('')
  const [agentFilter,setAgentFilter]=useState('')
  const [debouncedPipeline,setDebouncedPipeline]=useState('')
  const [debouncedAgent,setDebouncedAgent]=useState('')
  const [filterOptions,setFilterOptions]=useState<RunFilterOptions>({pipelines:[],agents:[]})
  const [loaded,setLoaded]=useState(false)
  const [activeId,setActiveId]=useState<string|null>(null)
  const [stepId,setStepId]=useState<string|null>(null)
  const [events,setEvents]=useState<RunEvent[]>([])
  const [tab,setTab]=useState<'overview'|'input'|'output'|'activity'|'logs'>('overview')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')

  async function refreshRuns(targetPage=page,targetStatus=statusFilter,targetPipeline=debouncedPipeline,targetAgent=debouncedAgent){
    try{
      const params=new URLSearchParams({page:String(targetPage)})
      if(targetStatus!=='all')params.set('status',targetStatus)
      if(targetPipeline.trim())params.set('pipeline',targetPipeline.trim())
      if(targetAgent.trim())params.set('agent',targetAgent.trim())
      const result=await api<RunPage>(`/runs/page?${params}`)
      setRuns(result.items);setTotal(result.total);setPage(result.page);setPages(result.pages);setLoaded(true)
      setActiveId(current=>current&&result.items.some(run=>run.id===current)?current:(result.items[0]?.id??null))
      setError('')
    }catch(reason){setError(reason instanceof Error?reason.message:t('runs.loadFailed'))}
  }

  useEffect(()=>{
    let cancelled=false
    api<RunFilterOptions>('/runs/filter-options').then(options=>{if(!cancelled)setFilterOptions(options)}).catch(()=>undefined)
    return()=>{cancelled=true}
  },[])
  useEffect(()=>{const timer=window.setTimeout(()=>{setDebouncedPipeline(pipelineFilter);setDebouncedAgent(agentFilter);setPage(1)},300);return()=>window.clearTimeout(timer)},[pipelineFilter,agentFilter])
  useEffect(()=>{
    let cancelled=false
    async function refresh(){if(!cancelled)await refreshRuns(page,statusFilter,debouncedPipeline,debouncedAgent)}
    refresh();const timer=window.setInterval(refresh,2000)
    return()=>{cancelled=true;window.clearInterval(timer)}
  },[page,statusFilter,debouncedPipeline,debouncedAgent])

  const active=useMemo(()=>runs.find(run=>run.id===activeId)??runs[0]??null,[runs,activeId])
  const step=useMemo(()=>active?.steps.find(item=>item.id===stepId)??active?.steps[0]??null,[active,stepId])
  useEffect(()=>{if(active&&!active.steps.some(item=>item.id===stepId))setStepId(active.steps[0]?.id??null)},[active,stepId])
  useEffect(()=>{
    if(!active)return
    let cancelled=false
    async function refreshEvents(){try{const items=await api<RunEvent[]>(`/runs/${active!.id}/events`);if(!cancelled)setEvents(items)}catch{/* next poll retries */}}
    refreshEvents();const timer=window.setInterval(refreshEvents,2000)
    return()=>{cancelled=true;window.clearInterval(timer)}
  },[active?.id])

  async function cancelRun(){
    if(!active)return
    setBusy(true)
    try{await api(`/runs/${active.id}/cancel`,{method:'POST'});await refreshRuns();toast(t('runs.cancelled',{sequence:active.sequence}),'warning',{kind:'run.cancelled',resource_type:'run',resource_id:active.id})}
    catch(reason){const message=reason instanceof Error?reason.message:t('runs.cancelFailed');setError(message);toast(message,'error')}
    finally{setBusy(false)}
  }
  async function retryRun(){
    if(!active)return
    setBusy(true)
    try{
      const created=await api<PipelineRun>(`/runs/${active.id}/retry`,{method:'POST'})
      setStatusFilter('all');setPipelineFilter('');setAgentFilter('');setDebouncedPipeline('');setDebouncedAgent('');setPage(1)
      await refreshRuns(1,'all','','');setActiveId(created.id);setStepId(created.steps[0]?.id??null);toast(t('runs.retried',{sequence:created.sequence}),'success',{kind:'run.retried',resource_type:'run',resource_id:created.id,payload:{source_run_id:active.id}})
    }catch(reason){setError(reason instanceof Error?reason.message:t('runs.retryFailed'))}
    finally{setBusy(false)}
  }

  const stepEvents=events.filter(event=>!step||event.step_run_id===step.id)
  const logs=stepEvents.filter(event=>event.kind==='worker.log')
  const runtime=(fallback:string,key?:string,params?:Record<string,unknown>)=>key?t(key,params):fallback
  return <div className="run-page">{error&&<div className="form-error page-error">{error}</div>}<section className="pipeline-run-registry"><div className="registry-title"><div><p className="eyebrow">{t('runs.eyebrow',{count:total.toString().padStart(2,'0')})}</p><h2>{t('runs.title')}</h2></div><span><Radio size={12}/>{t('runs.live')}</span></div><div className="run-filterbar"><div className="run-status-filters">{(['all','failed','succeeded'] as const).map(value=><button key={value} className={`chip ${statusFilter===value?'active':''}`} onClick={()=>{setStatusFilter(value);setPage(1)}}>{value==='all'?t('runs.all'):translateStatus(value)}</button>)}</div><label><span>{t('runs.pipeline').toUpperCase()}</span><input list="run-pipeline-options" value={pipelineFilter} onChange={event=>setPipelineFilter(event.target.value)} placeholder={t('runs.pipelinePlaceholder')}/><datalist id="run-pipeline-options">{filterOptions.pipelines.map(name=><option value={name} key={name}/>)}</datalist></label><label><span>{t('runs.agent').toUpperCase()}</span><input list="run-agent-options" value={agentFilter} onChange={event=>setAgentFilter(event.target.value)} placeholder={t('runs.agentPlaceholder')}/><datalist id="run-agent-options">{filterOptions.agents.map(name=><option value={name} key={name}/>)}</datalist></label></div>{runs.length?<><div className="run-history-head"><span>{t('runs.run').toUpperCase()}</span><span>{t('runs.pipeline').toUpperCase()}</span><span>{t('runs.trigger').toUpperCase()}</span><span>{t('runs.created').toUpperCase()}</span><span>{t('common.fields.status').toUpperCase()}</span></div>{runs.map(run=><button className={`run-history-row ${run.id===active?.id?'active':''}`} onClick={()=>{setActiveId(run.id);setStepId(run.steps[0]?.id??null)}} key={run.id}><strong>#{run.sequence}</strong><span>{run.pipeline_name||run.pipeline_id}</span><code>{translateTrigger(run.trigger_kind)}</code><time>{dateTime(run.created_at)}</time><em className={run.status}><i className={`status-dot ${run.status}`}/>{translateStatus(run.status)}</em></button>)}<div className="run-pagination"><button className="button ghost" disabled={page<=1} onClick={()=>setPage(value=>Math.max(1,value-1))}>{t('runs.previous')}</button><span>{t('runs.page',{page,pages})}</span><button className="button ghost" disabled={page>=pages} onClick={()=>setPage(value=>Math.min(pages,value+1))}>{t('runs.next')}</button></div></>:loaded&&<div className="run-list-empty"><Activity size={22}/><strong>{t('runs.emptyTitle')}</strong><span>{t('runs.emptyDescription')}</span></div>}</section>
    {active&&<>
    <header className="run-header"><div><div className="run-kicker"><span>RUN / {active.sequence}</span><span className="trigger-badge"><Zap size={12}/>{translateTrigger(active.trigger_kind)}</span><span className="trigger-badge">{active.engine.toUpperCase()}</span></div><p>{t('runs.pipeline').toUpperCase()}</p><h1>{active.pipeline_name||active.pipeline_id}</h1><small className="run-id">{active.id}</small></div><div className="run-actions">{(active.status==='queued'||active.status==='running')?<button className="button danger" disabled={busy} onClick={cancelRun}><Square size={14}/>{t('common.actions.stop')}</button>:<button className="button ghost" disabled={busy} onClick={retryRun}><RotateCcw size={14}/>{t('common.actions.retry')}</button>}<div className="run-status"><span className={`status-dot ${active.status}`}/>{translateStatus(active.status)}<small className="live-refresh">{t('runs.live')}</small></div></div></header>
    <section className="step-strip" style={{gridTemplateColumns:`repeat(${Math.max(active.steps.length,1)},minmax(150px,1fr))`}}>{active.steps.map(item=><button key={item.id} className={`step-card ${item.status} ${step?.id===item.id?'selected':''}`} onClick={()=>setStepId(item.id)}><div><span>{String(item.position+1).padStart(2,'0')}</span>{item.status==='succeeded'?<Check size={12}/>:null}</div><h3>{item.title}</h3><p>{item.agent_name}</p><small>{runtime(item.current_action,item.current_action_key,item.current_action_params)}</small></button>)}</section>
    {step&&<section className="run-detail no-artifacts"><aside className="run-summary"><p className="eyebrow">{t('runs.step').toUpperCase()} {String(step.position+1).padStart(2,'0')}</p><h2>{step.title}</h2><p>{step.agent_name}</p><div className="summary-stat"><span>{t('common.fields.status').toUpperCase()}</span><strong className={step.status}>{translateStatus(step.status)}</strong></div><div className="summary-stat"><span>{t('runs.progress').toUpperCase()}</span><strong>{step.progress}%</strong></div></aside><main className="work-detail"><nav className="detail-tabs">{(['overview','input','output','activity','logs'] as const).map(item=><button className={tab===item?'active':''} onClick={()=>setTab(item)} key={item}>{t(`runs.${item}`)}</button>)}</nav>
      {tab==='overview'&&<div className="detail-content"><div className="work-hero"><span><Activity size={18}/></span><div><p className="eyebrow">{t('runs.currentOperation')}</p><h2>{runtime(step.current_action,step.current_action_key,step.current_action_params)}</h2><p>{t('runs.refreshHint')}</p></div></div><div className="progress-track"><span style={{width:`${step.progress}%`}}/></div><div className="io-grid"><article><span><FileJson size={16}/>{t('runs.input').toUpperCase()}</span><pre>{JSON.stringify(step.input_payload,null,2)}</pre></article><span>→</span><article><span><ListTree size={16}/>{t('runs.output').toUpperCase()}</span><pre>{JSON.stringify(step.output_payload,null,2)}</pre></article></div></div>}
      {(tab==='input'||tab==='output')&&<div className="detail-content"><pre className="json-view">{JSON.stringify(tab==='input'?step.input_payload:step.output_payload,null,2)}</pre></div>}
      {tab==='activity'&&<div className="detail-content activity-list">{stepEvents.map(event=><div key={event.id}><span><Radio size={13}/></span><time>{time(event.created_at)}</time><p><strong>{runtime(event.title,event.title_key,event.title_params)}</strong>{(event.message||event.message_key)&&<small>{runtime(event.message,event.message_key,event.message_params)}</small>}</p></div>)}{!stepEvents.length&&<p className="event-empty">{t('runs.noEvents')}</p>}</div>}
      {tab==='logs'&&<div className="detail-content terminal"><div><TerminalSquare size={14}/>{t('runs.runtimeLogs').toUpperCase()}<span>{t('runs.logLines',{count:logs.length})}</span></div><pre>{logs.length?logs.map(event=>`[${time(event.created_at)}] ${runtime(event.message,event.message_key,event.message_params)}`).join('\n'):t('runs.noLogs')}</pre></div>}
    </main></section>}</>}
  </div>
}
