import { Bot, Box, Code2, Container, Cpu, ExternalLink, Server } from 'lucide-react'

export function DeploymentsPage() {
  return <div className="page"><header className="page-header"><div><p className="eyebrow">RUNTIME</p><h1>Ako sa agent nasadzuje</h1><p>Deployment závisí od typu agenta; pipeline vždy odkazuje na publikovanú verziu.</p></div></header>
    <div className="deployment-grid">
      <article className="deployment-card"><span><Bot/></span><p className="eyebrow">AI AGENT</p><h2>Managed AI runtime</h2><p>Agent nie je samostatný kontajner. Platforma spustí spoločný runner, vloží prompt, vstup a tools a zavolá zvolený model provider.</p><ul><li><Cpu size={14}/>Ollama alebo OpenAI-compatible API</li><li><Box size={14}/>Žiadny nový image pri zmene promptu</li><li><Server size={14}/>Runner lokálne alebo ako Kubernetes Job</li></ul></article>
      <article className="deployment-card"><span><Code2/></span><p className="eyebrow">SCRIPT AGENT</p><h2>Linux process</h2><p>Python, Node alebo Bash kód sa uloží s agentom a worker ho spustí priamo ako proces. Výstup stačí vypísať na stdout; worker ho automaticky prevedie na pomenovaný JSON kontrakt.</p><ul><li><Cpu size={14}/>Process executor na ľubovoľnom Linuxe</li><li><Box size={14}/>AF_INPUT_PATH a voliteľný AF_OUTPUT_PATH</li><li><Server size={14}/>Timeout, lease, logy a výsledok v GUI</li></ul></article>
      <article className="deployment-card"><span><Container/></span><p className="eyebrow">CUSTOM RUNTIME</p><h2>Vlastný OCI image</h2><p>Pre knižnice alebo systémové nástroje zadáš vlastný Podman/Docker image. Platforma mu odovzdá rovnaký input/output kontrakt.</p><ul><li><ExternalLink size={14}/>Image z ľubovoľného OCI registry</li><li><Box size={14}/>Pripnutie image digestu</li><li><Server size={14}/>Resource limity a network policy</li></ul></article>
    </div>
    <section className="panel deployment-flow"><div><strong>Agent draft</strong><small>prompt alebo kód</small></div><i>→</i><div><strong>Published version</strong><small>nemenný snapshot</small></div><i>→</i><div><strong>Runtime selection</strong><small>managed alebo OCI</small></div><i>→</i><div><strong>Execution target</strong><small>local / Kubernetes / OpenShift</small></div></section>
  </div>
}
