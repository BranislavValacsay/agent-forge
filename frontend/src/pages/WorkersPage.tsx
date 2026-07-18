import { useEffect, useMemo, useState } from 'react'
import { Ban, Check, Copy, Cpu, Plus, Power, Server, ShieldCheck, Trash2, Users, Wifi, WifiOff } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import type { Worker } from '../types'

const quote = (value:string) => `'${value.replaceAll("'", "'\\\"'\\\"'")}'`

export function WorkersPage() {
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
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Workers sa nepodarilo načítať') }
  }
  useEffect(() => { load(); const timer = window.setInterval(load, 15000); return () => window.clearInterval(timer) }, [])
  async function createToken() {
    try {
      const result = await api<{token:string}>('/workers/registration-tokens', { method:'POST', body:JSON.stringify({name_hint:name,expires_in_minutes:30}) })
      setToken(result.token); setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Token sa nepodarilo vytvoriť') }
  }
  async function disable(id:string) {
    await api(`/workers/${id}/disable`, {method:'POST'}); load();toast('Worker bol zakázaný.','warning',{kind:'worker.disabled',resource_type:'worker',resource_id:id})
  }
  async function enable(id:string) {
    await api(`/workers/${id}/enable`, {method:'POST'}); load();toast('Worker bol povolený.','success',{kind:'worker.enabled',resource_type:'worker',resource_id:id})
  }
  async function remove(worker:Worker) {
    await api(`/workers/${worker.id}`, {method:'DELETE'}); load();toast(`Worker „${worker.name}“ bol vymazaný.`,'success',{kind:'worker.deleted',resource_type:'worker',resource_id:worker.id})
  }
  async function copy() {
    await navigator.clipboard.writeText(command); setCopied(true); window.setTimeout(()=>setCopied(false),1500)
  }

  return <div className="page"><header className="page-header"><div><p className="eyebrow">EXECUTION FLEET / {workers.length.toString().padStart(2,'0')}</p><h1>Workers</h1><p>Ľubovoľný Linux počítač môže bezpečne preberať úlohy cez odchádzajúce HTTPS spojenie.</p></div><button className="button primary" onClick={createToken}><Plus size={16}/>Pridať worker</button></header>
    {error&&<div className="form-error page-error">{error}</div>}
    <section className="worker-overview"><article><Wifi size={18}/><strong>{workers.filter(w=>w.status==='online').length}</strong><span>ONLINE</span></article><article><WifiOff size={18}/><strong>{workers.filter(w=>w.status==='offline').length}</strong><span>OFFLINE</span></article><article><Cpu size={18}/><strong>{new Set(workers.flatMap(w=>w.executors)).size}</strong><span>EXECUTORS</span></article></section>
    <section className="panel worker-list"><div className="worker-row head"><span>WORKER</span><span>STAV</span><span>TRIEDA</span><span>EXECUTORY</span><span>PLATFORMA</span><span>HEARTBEAT</span><span/></div>{workers.map(worker=><div className="worker-row" key={worker.id}><span><i className={`status-dot ${worker.status}`}/><strong>{worker.name}</strong></span><span className={`worker-status ${worker.status}`}>{worker.status}</span><span className={`worker-class ${worker.worker_class}`}>{worker.worker_class}</span><span className="executor-tags">{worker.executors.map(item=><code key={item}>{item}</code>)}</span><span>{worker.platform} / {worker.architecture}<small>v{worker.version}</small></span><span>{new Date(worker.last_seen_at).toLocaleString('sk-SK')}</span><div className="worker-actions">{worker.status==='disabled'?<button className="icon-button" title="Povoliť worker" onClick={()=>enable(worker.id)}><Power size={13}/></button>:<button className="icon-button" title="Zakázať worker" onClick={()=>disable(worker.id)}><Ban size={13}/></button>}<button className="icon-button danger" title="Vymazať worker" onClick={()=>remove(worker)}><Trash2 size={13}/></button></div></div>)}{!workers.length&&<div className="dashboard-empty"><Server size={26}/><h3>Žiadny worker</h3><p>Klikni na Pridať worker a skopíruj vygenerované príkazy na ľubovoľný Linux počítač.</p></div>}</section>
    <section className="panel worker-security"><ShieldCheck size={18}/><div><h3>Sieťový model</h3><p>Worker iniciuje všetky spojenia smerom k API. Na worker stroji netreba otvárať žiadny port. Registračný token je jednorazový a platí 30 minút.</p></div></section>
    <section className="panel worker-security"><Users size={18}/><div><h3>CrewAI runtime</h3><p>CrewAI potrebuje rozšírený worker image. Registruj ho s executorom <code>crewai</code>; obyčajný Python worker CrewAI úlohy nepreberá. Pripravený image funguje v Podmane aj Kubernetes.</p></div></section>
    {token&&<div className="modal-backdrop" onMouseDown={()=>setToken('')}><div className="modal worker-modal" onMouseDown={event=>event.stopPropagation()}><p className="eyebrow">REGISTER WORKER</p><h2>Pripojiť Linux worker</h2><div className="form-grid"><label>Názov workera<input value={name} onChange={event=>setName(event.target.value)}/></label><label>Trieda workera<select value={workerClass} onChange={event=>{const value=event.target.value as typeof workerClass;setWorkerClass(value);setConcurrency(value==='gpu'?1:2)}}><option value="universal">Univerzálny</option><option value="cpu">CPU</option><option value="gpu">GPU</option></select></label><label>Paralelné úlohy<input type="number" min={1} max={64} value={concurrency} onChange={event=>setConcurrency(Math.max(1,Math.min(64,Number(event.target.value)||1)))}/></label></div><p className="worker-help">Spusť na cieľovom Linux počítači. Vyžaduje iba Python 3 a curl. Token sa po registrácii nedá použiť znova. Pre GPU zvoľ paralelizmus podľa dostupnej VRAM.</p><div className="command-block"><button onClick={copy}>{copied?<Check size={14}/>:<Copy size={14}/>} {copied?'Skopírované':'Kopírovať'}</button><pre>{command}</pre></div><div className="worker-doc-tabs"><div><strong>Foreground</strong><code>agent-forge-worker run --concurrency {concurrency}</code></div><div><strong>OpenRC</strong><code>command=/home/USER/.local/bin/agent-forge-worker</code></div><div><strong>systemd</strong><code>ExecStart=%h/.local/bin/agent-forge-worker run --concurrency {concurrency}</code></div></div><div className="modal-actions"><button className="button primary" onClick={()=>{setToken('');load()}}>Hotovo</button></div></div></div>}
  </div>
}
