import { useEffect, useState } from 'react'
import { Activity, Bot, GitBranch, Layers3, Plus, Zap } from 'lucide-react'
import { api } from '../lib/api'
import type { Agent, Pipeline, PipelineRun, Provider } from '../types'

export function Dashboard() {
  const [data,setData]=useState<{agents:Agent[];pipelines:Pipeline[];runs:PipelineRun[];providers:Provider[]}>({agents:[],pipelines:[],runs:[],providers:[]})
  useEffect(()=>{Promise.all([api<Agent[]>('/agents'),api<Pipeline[]>('/pipelines'),api<PipelineRun[]>('/runs'),api<Provider[]>('/providers')]).then(([agents,pipelines,runs,providers])=>setData({agents,pipelines,runs,providers})).catch(()=>undefined)},[])
  return <div className="page"><header className="page-header"><div><p className="eyebrow">CONTROL PLANE</p><h1>Agentická platforma</h1><p>Vytváraj, testuj a skladaj univerzálnych AI aj script agentov.</p></div></header>
    <div className="metric-grid"><Metric icon={<Bot/>} label="AGENTI" value={data.agents.length}/><Metric icon={<GitBranch/>} label="PIPELINE" value={data.pipelines.length}/><Metric icon={<Activity/>} label="SPUSTENIA" value={data.runs.length}/><Metric icon={<Layers3/>} label="DOSTUPNÉ MODELY" value={data.providers.reduce((sum,p)=>sum+p.model_count,0)}/></div>
    <section className="panel recent-panel"><div className="panel-title"><div><p className="eyebrow">RECENT RUNS</p><h2>Posledné spustenia</h2></div></div>{data.runs.map(run=><div className="run-row" key={run.id}><span className={`status-dot ${run.status}`}/><strong>RUN / {run.sequence}</strong><div><b>Pipeline {run.pipeline_id.slice(0,8)}</b><small>{run.trigger_kind.toUpperCase()} · {new Date(run.created_at).toLocaleString()}</small></div><span>{run.steps.length} krokov</span><span className="status-pill">{run.status.toUpperCase()}</span></div>)}
      {!data.runs.length&&<div className="dashboard-empty"><Zap size={23}/><h3>Žiadne historické spustenia</h3><p>Run sa tu objaví až po skutočnom spustení uloženej pipeline. Platforma nevytvára ukážkové dáta.</p></div>}
    </section>
  </div>
}

function Metric({icon,label,value}:{icon:React.ReactNode;label:string;value:number}){return <article><span className="metric-icon lime">{icon}</span><small>{label}</small><strong>{String(value).padStart(2,'0')}</strong><p>reálne uložené záznamy</p></article>}
