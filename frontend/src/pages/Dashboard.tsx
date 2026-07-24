import { useEffect, useState } from 'react'
import { Activity, Bot, GitBranch, Layers3, Plus, Zap } from 'lucide-react'
import { api } from '../lib/api'
import type { Agent, Pipeline, PipelineRun, Provider } from '../types'
import { translateStatus, translateTrigger, useI18n } from '../i18n'

export function Dashboard() {
  const { t, dateTime } = useI18n()
  const [data,setData]=useState<{agents:Agent[];pipelines:Pipeline[];runs:PipelineRun[];providers:Provider[]}>({agents:[],pipelines:[],runs:[],providers:[]})
  useEffect(()=>{Promise.all([api<Agent[]>('/agents'),api<Pipeline[]>('/pipelines'),api<PipelineRun[]>('/runs'),api<Provider[]>('/providers')]).then(([agents,pipelines,runs,providers])=>setData({agents,pipelines,runs,providers})).catch(()=>undefined)},[])
  return <div className="page"><header className="page-header"><div><p className="eyebrow">{t('dashboard.eyebrow')}</p><h1>{t('dashboard.title')}</h1><p>{t('dashboard.description')}</p></div></header>
    <div className="metric-grid"><Metric icon={<Bot/>} label={t('dashboard.metric.agents')} value={data.agents.length}/><Metric icon={<GitBranch/>} label={t('dashboard.metric.pipelines')} value={data.pipelines.length}/><Metric icon={<Activity/>} label={t('dashboard.metric.runs')} value={data.runs.length}/><Metric icon={<Layers3/>} label={t('dashboard.metric.models')} value={data.providers.reduce((sum,p)=>sum+p.model_count,0)}/></div>
    <section className="panel recent-panel"><div className="panel-title"><div><p className="eyebrow">{t('dashboard.recentEyebrow')}</p><h2>{t('dashboard.recentTitle')}</h2></div></div>{data.runs.map(run=><div className="run-row" key={run.id}><span className={`status-dot ${run.status}`}/><strong>RUN / {run.sequence}</strong><div><b>{t('dashboard.pipeline',{id:run.pipeline_id.slice(0,8)})}</b><small>{translateTrigger(run.trigger_kind)} · {dateTime(run.created_at)}</small></div><span>{t('dashboard.steps',{count:run.steps.length})}</span><span className="status-pill">{translateStatus(run.status)}</span></div>)}
      {!data.runs.length&&<div className="dashboard-empty"><Zap size={23}/><h3>{t('dashboard.emptyTitle')}</h3><p>{t('dashboard.emptyDescription')}</p></div>}
    </section>
  </div>
}

function Metric({icon,label,value}:{icon:React.ReactNode;label:string;value:number}){const {t}=useI18n();return <article><span className="metric-icon lime">{icon}</span><small>{label.toUpperCase()}</small><strong>{String(value).padStart(2,'0')}</strong><p>{t('common.records')}</p></article>}
