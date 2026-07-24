import { useEffect, useMemo, useState } from 'react'
import { Ban, Check, Copy, Cpu, Plus, Power, Server, ShieldCheck, Trash2, Users, Wifi, WifiOff } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { Worker } from '../types'
import { translateStatus, useI18n } from '../i18n'

const quote = (value:string) => `'${value.replaceAll("'", "'\\\"'\\\"'")}'`

export function WorkersPage() {
  const {t,dateTime}=useI18n()
  const [workers, setWorkers] = useState<Worker[]>([])
  const [token, setToken] = useState('')
  const [name, setName] = useState('linux-worker')
  const [workerClass, setWorkerClass] = useState<'cpu'|'gpu'|'universal'>('universal')
  const [concurrency, setConcurrency] = useState(2)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const origin = window.location.origin
  const command = useMemo(() => token ? [
    `curl -fsSL ${quote(`${origin}/api/v1/worker/install.sh`)} | AGENT_FORGE_URL=${quote(origin)} sh`,
    '',
    '~/.local/bin/agent-forge-worker register \\',
    `  --url ${quote(origin)} \\`,
    `  --token ${quote(token)} \\`,
    `  --name ${quote(name || 'linux-worker')} \\`,
    `  --class ${workerClass} \\`,
    '  --executors process,builtin,podman,managed-ai,mcp',
    '',
    `~/.local/bin/agent-forge-worker run --concurrency ${concurrency}`,
  ].join('\n') : '', [token, name, workerClass, concurrency, origin])

  async function load() {
    try { setWorkers(await api<Worker[]>('/workers')) }
    catch (reason) { setError(reason instanceof Error ? reason.message : t('workers.loadFailed')) }
  }
  useEffect(() => { load(); const timer = window.setInterval(load, 15000); return () => window.clearInterval(timer) }, [])
  async function createToken() {
    try {
      const result = await api<{token:string}>('/workers/registration-tokens', { method:'POST', body:JSON.stringify({name_hint:name,expires_in_minutes:30}) })
      setToken(result.token); setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('workers.tokenFailed')) }
  }
  async function disable(id:string) {
    await api(`/workers/${id}/disable`, {method:'POST'}); load();toast(t('workers.disabled'),'warning',{kind:'worker.disabled',resource_type:'worker',resource_id:id})
  }
  async function enable(id:string) {
    await api(`/workers/${id}/enable`, {method:'POST'}); load();toast(t('workers.enabled'),'success',{kind:'worker.enabled',resource_type:'worker',resource_id:id})
  }
  async function remove(worker:Worker) {
    await api(`/workers/${worker.id}`, {method:'DELETE'}); load();toast(t('workers.deleted',{name:worker.name}),'success',{kind:'worker.deleted',resource_type:'worker',resource_id:worker.id})
  }
  async function copy() {
    await navigator.clipboard.writeText(command); setCopied(true); window.setTimeout(()=>setCopied(false),1500)
  }

  return <div className="page"><header className="page-header"><div><p className="eyebrow">{t('workers.eyebrow',{count:workers.length.toString().padStart(2,'0')})}</p><h1>{t('workers.title')}</h1><p>{t('workers.description')}</p></div><button className="button primary" onClick={createToken}><Plus size={16}/>{t('workers.add')}</button></header>
    {error&&<div className="form-error page-error">{error}</div>}
    <section className="worker-overview"><article><Wifi size={18}/><strong>{workers.filter(w=>w.status==='online').length}</strong><span>{t('workers.online').toUpperCase()}</span></article><article><WifiOff size={18}/><strong>{workers.filter(w=>w.status==='offline').length}</strong><span>{t('workers.offline').toUpperCase()}</span></article><article><Cpu size={18}/><strong>{new Set(workers.flatMap(w=>w.executors)).size}</strong><span>{t('workers.executorCount').toUpperCase()}</span></article></section>
    <section className="panel worker-list"><div className="worker-row head"><span>WORKER</span><span>{t('common.fields.status').toUpperCase()}</span><span>{t('workers.class').toUpperCase()}</span><span>{t('workers.executors').toUpperCase()}</span><span>{t('workers.platform').toUpperCase()}</span><span>HEARTBEAT</span><span/></div>{workers.map(worker=><div className="worker-row" key={worker.id}><span><i className={`status-dot ${worker.status}`}/><strong>{worker.name}</strong></span><span className={`worker-status ${worker.status}`}>{translateStatus(worker.status)}</span><span className={`worker-class ${worker.worker_class}`}>{t(`workerClass.${worker.worker_class}`)}</span><span className="executor-tags">{worker.executors.map(item=><code key={item}>{item}</code>)}</span><span>{worker.platform} / {worker.architecture}<small>v{worker.version}</small></span><span>{dateTime(worker.last_seen_at)}</span><div className="worker-actions">{worker.status==='disabled'?<button className="icon-button" title={t('common.actions.enable')} onClick={()=>enable(worker.id)}><Power size={13}/></button>:<button className="icon-button" title={t('common.actions.disable')} onClick={()=>disable(worker.id)}><Ban size={13}/></button>}<button className="icon-button danger" title={t('common.actions.delete')} onClick={()=>remove(worker)}><Trash2 size={13}/></button></div></div>)}{!workers.length&&<div className="dashboard-empty"><Server size={26}/><h3>{t('workers.emptyTitle')}</h3><p>{t('workers.emptyDescription')}</p></div>}</section>
    <section className="panel worker-security"><ShieldCheck size={18}/><div><h3>{t('workers.networkTitle')}</h3><p>{t('workers.networkDescription')}</p></div></section>
    <section className="panel worker-security"><Users size={18}/><div><h3>{t('workers.crewaiTitle')}</h3><p>{t('workers.crewaiDescription')}</p></div></section>
    {token&&<div className="modal-backdrop" onMouseDown={()=>setToken('')}><div className="modal worker-modal" onMouseDown={event=>event.stopPropagation()}><p className="eyebrow">{t('workers.newEyebrow')}</p><h2>{t('workers.registerTitle')}</h2><div className="form-grid"><label>{t('workers.name')}<input value={name} onChange={event=>setName(event.target.value)}/></label><label>{t('workers.class')}<select value={workerClass} onChange={event=>{const value=event.target.value as typeof workerClass;setWorkerClass(value);setConcurrency(value==='gpu'?1:2)}}><option value="universal">{t('workerClass.universal')}</option><option value="cpu">{t('workerClass.cpu')}</option><option value="gpu">{t('workerClass.gpu')}</option></select></label><label>{t('workers.parallelTasks')}<input type="number" min={1} max={64} value={concurrency} onChange={event=>setConcurrency(Math.max(1,Math.min(64,Number(event.target.value)||1)))}/></label></div><p className="worker-help">{t('workers.help')}</p><div className="command-block"><button onClick={copy}>{copied?<Check size={14}/>:<Copy size={14}/>} {copied?t('workers.copied'):t('workers.copy')}</button><pre>{command}</pre></div><div className="worker-doc-tabs"><div><strong>Foreground</strong><code>agent-forge-worker run --concurrency {concurrency}</code></div><div><strong>OpenRC</strong><code>command=/home/USER/.local/bin/agent-forge-worker</code></div><div><strong>systemd</strong><code>ExecStart=%h/.local/bin/agent-forge-worker run --concurrency {concurrency}</code></div></div><div className="modal-actions"><button className="button primary" onClick={()=>{setToken('');load()}}>{t('workers.done')}</button></div></div></div>}
  </div>
}
