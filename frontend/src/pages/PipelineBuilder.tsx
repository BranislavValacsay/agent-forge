import { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background, Controls, Edge, Handle, MiniMap, Node, NodeProps, Position,
  ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, useUpdateNodeInternals,
} from '@xyflow/react'
import { AlertTriangle, ArrowLeft, Bot, Braces, Check, Code2, Database, Edit3, GitBranch, GripVertical, Link2, Play, PlugZap, Plus, Save, Search, Settings2, Trash2, Users, Zap } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { compatible, portsToSchema, schemaToPorts, type PortDefinition, type ValueMapping } from '../lib/contracts'
import type { Agent, Pipeline, PipelineRun } from '../types'

type NodeKind = 'agent' | 'trigger' | 'transform' | 'output'
type FlowData = {
  label:string;nodeKind:NodeKind;agentName?:string;agentId?:string;detail:string
  inputs:PortDefinition[];outputs:PortDefinition[];config?:Record<string,unknown>
}
type EdgeData = { kind:'value';mapping:ValueMapping } | { kind:'control' }

type ValueEdge=Edge<EdgeData>&{data:{kind:'value';mapping:ValueMapping}}
const isValueEdge=(edge:Edge<EdgeData>):edge is ValueEdge=>(edge.data?.kind??'value')==='value'&&!!(edge.data as {mapping?:ValueMapping}|undefined)?.mapping

const colors:Record<NodeKind,string>={agent:'#baff29',trigger:'#f0b84b',transform:'#8ea9ff',output:'#ce8cff'}
const agentRuntime=(agent:Agent)=>agent.kind==='script'?'Process runtime':agent.kind==='mcp'?'MCP tool':agent.kind==='crewai'?'CrewAI tím':'Managed AI runtime'

function FlowNode({id,data,selected}:NodeProps<Node<FlowData>>){
  const updateNodeInternals=useUpdateNodeInternals()
  useEffect(()=>updateNodeInternals(id),[id,data.inputs,data.outputs,updateNodeInternals])
  const icon=data.nodeKind==='agent'?<Bot size={15}/>:data.nodeKind==='trigger'?<Zap size={15}/>:data.nodeKind==='transform'?<Braces size={15}/>:<Database size={15}/>
  const rows=Math.max(data.inputs.length,data.outputs.length,1)
  return <div className={`flow-node typed ${selected?'selected':''}`} style={{'--node-accent':colors[data.nodeKind],minHeight:112+rows*25} as React.CSSProperties}>
    {data.nodeKind!=='trigger'&&<Handle id="control-in" type="target" position={Position.Top} className="control-handle control-in" title="Poradie vykonania"/>}
    <div className="flow-node-top"><span>{icon}{data.nodeKind.toUpperCase()}</span><GripVertical size={14}/></div>
    <h3>{data.label}</h3><p>{data.agentName??data.detail}</p>
    <div className="node-ports">
      <div>{data.inputs.map((port,index)=><div className="node-port input" key={port.name}><Handle id={`in:${port.name}`} type="target" position={Position.Left} style={{top:100+index*25}}/><span>{port.name}</span><small>{port.type}{port.required?'*':''}</small></div>)}</div>
      <div>{data.outputs.map((port,index)=><div className="node-port output" key={port.name}><span>{port.name}</span><small>{port.type}</small><Handle id={`out:${port.name}`} type="source" position={Position.Right} style={{top:100+index*25}}/></div>)}</div>
    </div>
    {!data.inputs.length&&!data.outputs.length&&<small className="no-ports">Bez dátových portov · FLOW je dostupný</small>}
    {data.nodeKind!=='output'&&<Handle id="control-out" type="source" position={Position.Bottom} className="control-handle control-out" title="Poradie vykonania"/>}
  </div>
}

const nodeTypes={flowNode:FlowNode}

function Builder({initialAgent,initialPipeline,onBack}:{initialAgent?:Agent;initialPipeline?:Pipeline;onBack?:()=>void}){
  const [nodes,setNodes,onNodesChange]=useNodesState<Node<FlowData>>([])
  const [edges,setEdges,onEdgesChange]=useEdgesState<Edge<EdgeData>>([])
  const [agents,setAgents]=useState<Agent[]>([])
  const [saved,setSaved]=useState(true)
  const [selectedNodeId,setSelectedNodeId]=useState<string|null>(null)
  const [selectedEdgeId,setSelectedEdgeId]=useState<string|null>(null)
  const [pipelineId,setPipelineId]=useState<string|null>(null)
  const [name,setName]=useState('Untitled pipeline')
  const [engine,setEngine]=useState<'legacy'|'langgraph'>('langgraph')
  const [error,setError]=useState('')
  const initialized=useRef(false)
  const selectedNode=useMemo(()=>nodes.find(node=>node.id===selectedNodeId)??null,[nodes,selectedNodeId])
  const selectedEdge=useMemo(()=>edges.find(edge=>edge.id===selectedEdgeId)??null,[edges,selectedEdgeId])
  useEffect(()=>{api<Agent[]>('/agents').then(setAgents).catch(()=>setAgents([]))},[])
  useEffect(()=>{
    if(!initialPipeline||initialized.current)return
    initialized.current=true
    setNodes(initialPipeline.graph.nodes as Node<FlowData>[])
    setEdges(initialPipeline.graph.edges as Edge<EdgeData>[])
    setPipelineId(initialPipeline.id);setName(initialPipeline.name);setEngine(initialPipeline.engine);setSaved(true)
  },[initialPipeline,setEdges,setNodes])
  useEffect(()=>{
    if(!initialAgent||initialized.current)return
    initialized.current=true
    const agentInputs=schemaToPorts(initialAgent.input_schema)
    const agentOutputs=schemaToPorts(initialAgent.output_schema)
    const effectiveOutputs=agentOutputs.length?agentOutputs:[{name:'result',type:'string' as const,required:false,description:'Výsledok agenta'}]
    const triggerId='quick-trigger',agentId='quick-agent',outputId='quick-output'
    setNodes([
      {id:triggerId,type:'flowNode',position:{x:60,y:160},data:{label:'Manual trigger',nodeKind:'trigger',detail:'manual',inputs:[],outputs:agentInputs,config:{triggerKind:'manual'}}},
      {id:agentId,type:'flowNode',position:{x:370,y:160},data:{label:initialAgent.name,nodeKind:'agent',agentName:initialAgent.name,agentId:initialAgent.id,detail:agentRuntime(initialAgent),inputs:agentInputs,outputs:effectiveOutputs}},
      {id:outputId,type:'flowNode',position:{x:680,y:160},data:{label:'Pipeline output',nodeKind:'output',detail:'Výsledok testu',inputs:effectiveOutputs,outputs:[],config:{outputType:'json'}}},
    ])
    const controlEdges:Edge<EdgeData>[]=[
      {id:'flow-trigger-agent',source:triggerId,target:agentId,sourceHandle:'control-out',targetHandle:'control-in',data:{kind:'control'},label:'FLOW',className:'control-edge'},
      {id:'flow-agent-output',source:agentId,target:outputId,sourceHandle:'control-out',targetHandle:'control-in',data:{kind:'control'},label:'FLOW',className:'control-edge'},
    ]
    const inputEdges:Edge<EdgeData>[] = agentInputs.map(port=>({id:`input-${port.name}`,source:triggerId,target:agentId,sourceHandle:`out:${port.name}`,targetHandle:`in:${port.name}`,data:{kind:'value',mapping:{source:port.name,target:port.name,sourceType:port.type,targetType:port.type}},label:`${port.name} → ${port.name}`,className:'typed-edge'}))
    const outputEdges:Edge<EdgeData>[] = effectiveOutputs.map(port=>({id:`output-${port.name}`,source:agentId,target:outputId,sourceHandle:`out:${port.name}`,targetHandle:`in:${port.name}`,data:{kind:'value',mapping:{source:port.name,target:port.name,sourceType:port.type,targetType:port.type}},label:`${port.name} → ${port.name}`,className:'typed-edge'}))
    setEdges([...controlEdges,...inputEdges,...outputEdges]);setName(`Test: ${initialAgent.name}`);setSelectedNodeId(agentId);setSaved(false)
  },[initialAgent,setEdges,setNodes])

  const onConnect=useCallback((connection:{source:string;target:string;sourceHandle:string|null;targetHandle:string|null})=>{
    const sourceNode=nodes.find(node=>node.id===connection.source);const targetNode=nodes.find(node=>node.id===connection.target)
    if(connection.sourceHandle==='control-out'&&connection.targetHandle==='control-in'){
      const edge:Edge<EdgeData>={id:`flow-${Date.now()}-${Math.random().toString(16).slice(2)}`,source:connection.source,target:connection.target,sourceHandle:'control-out',targetHandle:'control-in',data:{kind:'control'},label:'FLOW',className:'control-edge'}
      setEdges(current=>current.some(item=>item.source===edge.source&&item.target===edge.target&&item.data?.kind==='control')?current:[...current,edge]);setSelectedEdgeId(edge.id);setSelectedNodeId(null);setSaved(false);setError('');return
    }
    const sourceName=connection.sourceHandle?.replace(/^out:/,'');const targetName=connection.targetHandle?.replace(/^in:/,'')
    const sourcePort=sourceNode?.data.outputs.find(port=>port.name===sourceName);const targetPort=targetNode?.data.inputs.find(port=>port.name===targetName)
    if(!sourcePort||!targetPort){setError('Spojenie musí viesť z konkrétneho výstupného portu do konkrétneho vstupného portu.');return}
    if(!compatible(sourcePort.type,targetPort.type)){setError(`Nekompatibilné typy: ${sourcePort.type} → ${targetPort.type}`);return}
    const mapping:ValueMapping={source:sourcePort.name,target:targetPort.name,sourceType:sourcePort.type,targetType:targetPort.type}
    const edge:Edge<EdgeData>={id:`edge-${Date.now()}-${Math.random().toString(16).slice(2)}`,source:connection.source,target:connection.target,sourceHandle:connection.sourceHandle,targetHandle:connection.targetHandle,data:{kind:'value',mapping},label:`${mapping.source} → ${mapping.target}`,className:'typed-edge'}
    setEdges(current=>[...current.filter(item=>!(item.target===edge.target&&item.targetHandle===edge.targetHandle)),edge]);setSelectedEdgeId(edge.id);setSelectedNodeId(null);setSaved(false);setError('')
  },[nodes,setEdges])

  const addNode=useCallback((kind:NodeKind,agent?:Agent,position?:{x:number;y:number})=>{
    const id=`${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const defaults:Record<NodeKind,FlowData>={
      agent:{label:agent?.name??'Agent',nodeKind:'agent',agentName:agent?.name??'Unassigned',agentId:agent?.id,detail:agent?agentRuntime(agent):'Runtime neurčený',inputs:agent?schemaToPorts(agent.input_schema):[],outputs:agent?schemaToPorts(agent.output_schema):[]},
      trigger:{label:'Manual trigger',nodeKind:'trigger',detail:'manual',inputs:[],outputs:[],config:{triggerKind:'manual'}},
      transform:{label:'Transform',nodeKind:'transform',detail:'Map input → output',inputs:[{name:'value',type:'any',required:true}],outputs:[{name:'result',type:'any'}],config:{expression:'$input.value'}},
      output:{label:'Pipeline output',nodeKind:'output',detail:'Pipeline results',inputs:[],outputs:[],config:{outputType:'json'}},
    }
    setNodes(current=>[...current,{id,type:'flowNode',position:position??{x:100+current.length*270,y:150},data:defaults[kind]}]);setSelectedNodeId(id);setSelectedEdgeId(null);setSaved(false)
  },[setNodes])

  const onDrop=useCallback((event:DragEvent)=>{event.preventDefault();const kind=event.dataTransfer.getData('node-kind') as NodeKind;if(!kind)return;const agent=agents.find(item=>item.id===event.dataTransfer.getData('agent-id'));const bounds=event.currentTarget.getBoundingClientRect();addNode(kind,agent,{x:event.clientX-bounds.left-105,y:event.clientY-bounds.top-55})},[addNode,agents])
  function removeSelected(){if(selectedNodeId){setNodes(current=>current.filter(node=>node.id!==selectedNodeId));setEdges(current=>current.filter(edge=>edge.source!==selectedNodeId&&edge.target!==selectedNodeId));setSelectedNodeId(null)}else if(selectedEdgeId){setEdges(current=>current.filter(edge=>edge.id!==selectedEdgeId));setSelectedEdgeId(null)}setSaved(false)}
  function patchNode(patch:Partial<FlowData>){if(!selectedNodeId)return;setNodes(current=>current.map(node=>node.id===selectedNodeId?{...node,data:{...node.data,...patch}}:node));setSaved(false)}
  function patchNodePorts(direction:'inputs'|'outputs',ports:PortDefinition[]){
    if(!selectedNodeId||!selectedNode)return
    const previous=selectedNode.data[direction]
    setEdges(current=>current.flatMap(edge=>{
      if(!isValueEdge(edge))return[edge]
      const attached=direction==='outputs'?edge.source===selectedNodeId:edge.target===selectedNodeId
      if(!attached)return[edge]
      const mappedName=direction==='outputs'?edge.data.mapping.source:edge.data.mapping.target
      const oldIndex=previous.findIndex(port=>port.name===mappedName)
      if(oldIndex<0)return[edge]
      const oldPort=previous[oldIndex]
      const sameName=ports.find(port=>port.name===oldPort.name)
      let nextPort=sameName
      if(!nextPort&&ports[oldIndex]&&!previous.some(port=>port.name===ports[oldIndex].name))nextPort=ports[oldIndex]
      if(!nextPort)return[]
      const mapping=direction==='outputs'?{...edge.data.mapping,source:nextPort.name,sourceType:nextPort.type}:{...edge.data.mapping,target:nextPort.name,targetType:nextPort.type}
      return[{...edge,sourceHandle:`out:${mapping.source}`,targetHandle:`in:${mapping.target}`,data:{kind:'value' as const,mapping},label:`${mapping.source} → ${mapping.target}`}]
    }))
    patchNode({[direction]:ports} as Partial<FlowData>)
  }
  function patchMapping(patch:Partial<ValueMapping>){if(!selectedEdgeId)return;setEdges(current=>current.map(edge=>{if(edge.id!==selectedEdgeId||!isValueEdge(edge))return edge;const mapping={...edge.data.mapping,...patch};return{...edge,sourceHandle:`out:${mapping.source}`,targetHandle:`in:${mapping.target}`,data:{kind:'value',mapping},label:`${mapping.source} → ${mapping.target}`}}));setSaved(false)}
  function validationErrors(){const issues:string[]=[];for(const node of nodes){for(const port of node.data.inputs.filter(port=>port.required)){if(!edges.some(edge=>edge.target===node.id&&isValueEdge(edge)&&edge.data.mapping.target===port.name))issues.push(`${node.data.label}: chýba povinný vstup „${port.name}“`)}for(const port of node.data.inputs){const incoming=edges.filter(edge=>edge.target===node.id&&isValueEdge(edge)&&edge.data.mapping.target===port.name);if(incoming.length>1)issues.push(`${node.data.label}: vstup „${port.name}“ má viac zdrojov`)}}for(const edge of edges){if(isValueEdge(edge)&&!compatible(edge.data.mapping.sourceType,edge.data.mapping.targetType))issues.push(`Nekompatibilné mapovanie ${edge.data.mapping.source} → ${edge.data.mapping.target}`)}return issues}
  async function save():Promise<string|null>{const issues=validationErrors();if(issues.length){setError(issues.join(' · '));return null}setError('');const trigger=nodes.find(node=>node.data.nodeKind==='trigger');const slugBase=name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'pipeline';const payload={name,slug:`${slugBase}-${pipelineId?pipelineId.slice(0,6):Date.now().toString().slice(-6)}`,description:'',visibility:'private',graph:{nodes,edges},input_schema:portsToSchema(trigger?.data.outputs??[]),engine};try{const validation=await api<{valid:boolean;errors:string[];warnings:string[]}>('/pipelines/validate-draft',{method:'POST',body:JSON.stringify(payload)});if(!validation.valid){setError(validation.errors.join(' · '));return null}let id=pipelineId;if(id)await api<Pipeline>(`/pipelines/${id}`,{method:'PUT',body:JSON.stringify(payload)});else{id=(await api<Pipeline>('/pipelines',{method:'POST',body:JSON.stringify(payload)})).id;setPipelineId(id)}setSaved(true);return id}catch(reason){setError(reason instanceof Error?reason.message:'Pipeline sa nepodarilo uložiť');return null}}
  async function runPipeline(){setError('');const id=pipelineId??await save();if(!id)return;try{const run=await api<PipelineRun>(`/pipelines/${id}/runs`,{method:'POST',body:JSON.stringify({trigger_kind:'manual',input_payload:{}})});toast(`Pipeline bola spustená ako run #${run.sequence}.`,'success',{kind:'pipeline.started',resource_type:'pipeline',resource_id:id,payload:{run_id:run.id}})}catch(reason){const message=reason instanceof Error?reason.message:'Pipeline sa nepodarilo spustiť';setError(message);toast(message,'error')}}

  const sourceNode=selectedEdge?nodes.find(node=>node.id===selectedEdge.source):null;const targetNode=selectedEdge?nodes.find(node=>node.id===selectedEdge.target):null
  const selectedValueEdge=selectedEdge&&isValueEdge(selectedEdge)?selectedEdge:null
  return <div className="builder-shell"><div className="builder-top">{onBack&&<button className="icon-button" onClick={onBack} title="Späť na pipeline"><ArrowLeft size={16}/></button>}<div><p className="eyebrow">PIPELINE / {pipelineId?'EDIT':'NEW DRAFT'}</p><input className="pipeline-name" value={name} onChange={event=>{setName(event.target.value);setSaved(false)}}/></div><label className="engine-select"><span>ENGINE</span><select value={engine} onChange={event=>{setEngine(event.target.value as 'legacy'|'langgraph');setSaved(false)}}><option value="langgraph">LangGraph</option><option value="legacy">Legacy</option></select></label><span className="save-state"><Check size={13}/>{saved?'Všetky zmeny uložené':'Neuložené zmeny'}</span><button className="button ghost" onClick={save}><Save size={15}/>Uložiť</button><button className="button primary" onClick={runPipeline} disabled={!nodes.length}><Play size={15}/>Uložiť a spustiť</button></div>
    {error&&<div className="builder-error"><AlertTriangle size={13}/>{error}</div>}
    <div className="builder-body"><aside className="node-palette"><p className="eyebrow">NODES</p><div className="search small"><Search size={14}/><input placeholder="Hľadať…"/></div><p className="palette-label">CONTROL</p><Palette kind="trigger" icon={<Zap size={16}/>} title="Trigger" detail="Pipeline inputs"/><Palette kind="transform" icon={<Braces size={16}/>} title="Transform" detail="Mapovanie dát"/><Palette kind="output" icon={<Database size={16}/>} title="Output" detail="Pipeline results"/><p className="palette-label">AGENTI</p>{agents.map(agent=><Palette key={agent.id} kind="agent" agentId={agent.id} icon={agent.kind==='ai'?<Bot size={16}/>:agent.kind==='crewai'?<Users size={16}/>:agent.kind==='mcp'?<PlugZap size={16}/>:<Code2 size={16}/>} title={agent.name} detail={`${schemaToPorts(agent.input_schema).length} in · ${schemaToPorts(agent.output_schema).length} out`}/>)}{!agents.length&&<p className="palette-empty">Najprv vytvor agenta a definuj jeho vstupy a výstupy.</p>}</aside>
    <main className="flow-canvas" onDrop={onDrop} onDragOver={event=>{event.preventDefault();event.dataTransfer.dropEffect='move'}}>{!nodes.length&&<div className="canvas-empty"><Zap size={25}/><h2>Prázdna pipeline</h2><p>Presuň sem trigger, agenta, transform alebo output.</p></div>}<ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes=>{onNodesChange(changes);setSaved(false)}} onEdgesChange={changes=>{onEdgesChange(changes);setSaved(false)}} onConnect={onConnect} onNodeClick={(_,node)=>{setSelectedNodeId(node.id);setSelectedEdgeId(null)}} onEdgeClick={(_,edge)=>{setSelectedEdgeId(edge.id);setSelectedNodeId(null)}} onPaneClick={()=>{setSelectedNodeId(null);setSelectedEdgeId(null)}} deleteKeyCode={['Backspace','Delete']} onNodesDelete={deleted=>{const ids=new Set(deleted.map(node=>node.id));setEdges(current=>current.filter(edge=>!ids.has(edge.source)&&!ids.has(edge.target)));setSelectedNodeId(null);setSaved(false)}} fitView minZoom={.45} maxZoom={1.5}><Background color="#303431" gap={24} size={1}/><MiniMap pannable zoomable nodeColor={node=>colors[(node.data as FlowData).nodeKind]} maskColor="rgba(8,10,9,.72)"/><Controls/></ReactFlow></main>
    <aside className="inspector"><div className="inspector-title"><div><p className="eyebrow">INSPECTOR</p><h3>{selectedNode?.data.label??(selectedEdge?'Value mapping':'Pipeline')}</h3></div>{selectedEdge?<Link2 size={17}/>:<Settings2 size={17}/>}</div>
      {selectedNode&&<><label>Názov<input value={selectedNode.data.label} onChange={event=>patchNode({label:event.target.value})}/></label>{selectedNode.data.nodeKind==='agent'?<><p className="inspector-copy">Porty môžeš doplniť aj pre staršieho agenta. FLOW spojenie určuje poradie, dátové porty prenášajú hodnoty.</p><InlinePorts title="INPUTS" ports={selectedNode.data.inputs} onChange={ports=>patchNodePorts('inputs',ports)}/><InlinePorts title="OUTPUTS" ports={selectedNode.data.outputs} onChange={ports=>patchNodePorts('outputs',ports)}/></>:<>{selectedNode.data.nodeKind!=='trigger'&&<InlinePorts title={selectedNode.data.nodeKind==='output'?'PIPELINE RESULTS':'INPUTS'} ports={selectedNode.data.inputs} onChange={ports=>patchNodePorts('inputs',ports)}/>} {selectedNode.data.nodeKind!=='output'&&<InlinePorts title={selectedNode.data.nodeKind==='trigger'?'PIPELINE INPUTS':'OUTPUTS'} ports={selectedNode.data.outputs} onChange={ports=>patchNodePorts('outputs',ports)}/>}</>}{selectedNode.data.nodeKind==='trigger'&&<label>Trigger<select value={String(selectedNode.data.config?.triggerKind??'manual')} onChange={event=>patchNode({detail:event.target.value,config:{...selectedNode.data.config,triggerKind:event.target.value}})}><option value="manual">Manual</option><option value="cron">Cron</option><option value="api">Called / API</option></select></label>}{selectedNode.data.nodeKind==='transform'&&<label>Výraz<textarea defaultValue={String(selectedNode.data.config?.expression??'$input.value')} onChange={event=>patchNode({config:{...selectedNode.data.config,expression:event.target.value}})}/></label>}<button className="button danger wide" onClick={removeSelected}><Trash2 size={15}/>Odstrániť node</button></>}
      {selectedEdge&&sourceNode&&targetNode&&<><div className="mapping-flow"><strong>{sourceNode.data.label}</strong><span>→</span><strong>{targetNode.data.label}</strong></div>{selectedValueEdge?<><label>Zdrojový výstup<select value={selectedValueEdge.data.mapping.source} onChange={event=>{const port=sourceNode.data.outputs.find(item=>item.name===event.target.value);if(port)patchMapping({source:port.name,sourceType:port.type})}}>{sourceNode.data.outputs.map(port=><option value={port.name} key={port.name}>{port.name} : {port.type}</option>)}</select></label><label>Cieľový vstup<select value={selectedValueEdge.data.mapping.target} onChange={event=>{const port=targetNode.data.inputs.find(item=>item.name===event.target.value);if(port)patchMapping({target:port.name,targetType:port.type})}}>{targetNode.data.inputs.map(port=><option value={port.name} key={port.name}>{port.name} : {port.type}</option>)}</select></label><div className={`mapping-compat ${compatible(selectedValueEdge.data.mapping.sourceType,selectedValueEdge.data.mapping.targetType)?'ok':'bad'}`}>{compatible(selectedValueEdge.data.mapping.sourceType,selectedValueEdge.data.mapping.targetType)?'Typy sú kompatibilné':'Typy nie sú kompatibilné'}</div></>:<p className="inspector-copy">Control FLOW určuje poradie vykonania. Neprenáša dátovú hodnotu.</p>}<button className="button danger wide" onClick={removeSelected}><Trash2 size={15}/>Odstrániť spojenie</button></>}
      {!selectedNode&&!selectedEdge&&<><p className="inspector-copy">FLOW aj dátové hrany tvoria DAG. Jeden výstup môže napájať viac vetiev; každá vetva dostane vlastný pomenovaný vstup a pripravené vetvy sa spúšťajú paralelne.</p><div className="schema-box"><small>PARALLEL DAG</small><code>{nodes.length} nodes · {edges.length} connections</code></div></>}
    </aside></div></div>
}

function ContractSummary({title,ports}:{title:string;ports:PortDefinition[]}){return <div className="contract-summary"><small>{title}</small>{ports.map(port=><div key={port.name}><code>{port.name}</code><span>{port.type}{port.required?' · required':''}</span></div>)}{!ports.length&&<p>Žiadne porty</p>}</div>}
function InlinePorts({title,ports,onChange}:{title:string;ports:PortDefinition[];onChange:(ports:PortDefinition[])=>void}){function patch(index:number,value:Partial<PortDefinition>){onChange(ports.map((port,i)=>i===index?{...port,...value}:port))}return <div className="inline-ports"><div><small>{title}</small><button type="button" onClick={()=>onChange([...ports,{name:`value_${ports.length+1}`,type:'string',required:true}])}><Plus size={12}/></button></div>{ports.map((port,index)=><section key={index}><input value={port.name} onChange={event=>patch(index,{name:event.target.value.replace(/[^a-zA-Z0-9_.-]/g,'_')})}/><select value={port.type} onChange={event=>patch(index,{type:event.target.value as PortDefinition['type']})}><option value="string">string</option><option value="json">json</option><option value="number">number</option><option value="boolean">boolean</option><option value="file">file</option><option value="image">image</option><option value="any">any</option></select><label title="Povinný"><input type="checkbox" checked={port.required} onChange={event=>patch(index,{required:event.target.checked})}/>*</label><button type="button" onClick={()=>onChange(ports.filter((_,i)=>i!==index))}><Trash2 size={12}/></button></section>)}{!ports.length&&<p>Žiadne porty</p>}</div>}
function Palette({kind,agentId,icon,title,detail}:{kind:NodeKind;agentId?:string;icon:React.ReactNode;title:string;detail:string}){return <div draggable onDragStart={event=>{event.dataTransfer.setData('node-kind',kind);if(agentId)event.dataTransfer.setData('agent-id',agentId)}} className="palette-item"><span>{icon}</span><div><strong>{title}</strong><small>{detail}</small></div><GripVertical size={14}/></div>}
export function PipelineBuilder({initialAgent}:{initialAgent?:Agent}){
  const [pipelines,setPipelines]=useState<Pipeline[]>([])
  const [editing,setEditing]=useState<Pipeline|null|undefined>(initialAgent?null:undefined)
  const [loading,setLoading]=useState(!initialAgent)
  const [runs,setRuns]=useState<PipelineRun[]>([])
  const [renameTarget,setRenameTarget]=useState<Pipeline|null>(null)
  const [renameValue,setRenameValue]=useState('')
  const [starting,setStarting]=useState<string|null>(null)
  async function load(){setLoading(true);try{setPipelines(await api<Pipeline[]>('/pipelines'))}finally{setLoading(false)}}
  async function loadRuns(){try{setRuns(await api<PipelineRun[]>('/runs'))}catch{/* next poll retries */}}
  async function renamePipeline(){
    const pipeline=renameTarget;const value=renameValue.trim()
    if(!pipeline||!value||value===pipeline.name){setRenameTarget(null);return}
    try{
      const updated=await api<Pipeline>(`/pipelines/${pipeline.id}`,{method:'PUT',body:JSON.stringify({name:value,slug:pipeline.slug,description:pipeline.description,visibility:pipeline.visibility,graph:pipeline.graph,input_schema:pipeline.input_schema,engine:pipeline.engine})})
      setPipelines(current=>current.map(item=>item.id===updated.id?updated:item));setRenameTarget(null);toast(`Pipeline bola premenovaná na „${value}“.`, 'success',{kind:'pipeline.renamed',resource_type:'pipeline',resource_id:pipeline.id})
    }catch(reason){toast(reason instanceof Error?reason.message:'Pipeline sa nepodarilo premenovať','error')}
  }
  async function removePipeline(pipeline:Pipeline){
    try{await api(`/pipelines/${pipeline.id}`,{method:'DELETE'});setPipelines(current=>current.filter(item=>item.id!==pipeline.id));toast(`Pipeline „${pipeline.name}“ bola vymazaná. História behov zostala zachovaná.`,'success',{kind:'pipeline.deleted',resource_type:'pipeline',resource_id:pipeline.id})}
    catch(reason){toast(reason instanceof Error?reason.message:'Pipeline sa nepodarilo vymazať','error')}
  }
  async function startPipeline(pipeline:Pipeline){setStarting(pipeline.id);try{const run=await api<PipelineRun>(`/pipelines/${pipeline.id}/runs`,{method:'POST',body:JSON.stringify({trigger_kind:'manual',input_payload:{}})});setRuns(current=>[run,...current]);toast(`Pipeline „${pipeline.name}“ beží ako run #${run.sequence}.`,'success',{kind:'pipeline.started',resource_type:'pipeline',resource_id:pipeline.id,payload:{run_id:run.id}})}catch(reason){toast(reason instanceof Error?reason.message:'Pipeline sa nepodarilo spustiť','error')}finally{setStarting(null)}}
  useEffect(()=>{if(!initialAgent)load()},[initialAgent])
  useEffect(()=>{if(initialAgent||editing!==undefined)return;loadRuns();const timer=window.setInterval(loadRuns,2000);return()=>window.clearInterval(timer)},[initialAgent,editing])
  if(initialAgent||editing!==undefined)return <ReactFlowProvider><Builder initialAgent={initialAgent} initialPipeline={editing??undefined} onBack={initialAgent?undefined:()=>{setEditing(undefined);load()}}/></ReactFlowProvider>
  return <div className="page pipeline-catalog"><header className="page-header"><div><p className="eyebrow">PIPELINE REGISTRY / {pipelines.length.toString().padStart(2,'0')}</p><h1>Pipeline</h1><p>Otvor existujúci workflow alebo vytvor nový prázdny graf.</p></div><button className="button primary" onClick={()=>setEditing(null)}><Plus size={16}/>Nová pipeline</button></header>
    <div className="pipeline-list">{pipelines.map(pipeline=>{const last=runs.find(run=>run.pipeline_id===pipeline.id);const active=last&&(last.status==='queued'||last.status==='running');return <article key={pipeline.id}><span><GitBranch size={18}/></span><div><small>{pipeline.visibility.toUpperCase()} · {pipeline.engine.toUpperCase()}</small><h2>{pipeline.name}</h2><p>{pipeline.description||`${pipeline.graph.nodes.length} nodes · ${pipeline.graph.edges.length} connections`}</p><time>Upravené {new Date(pipeline.updated_at).toLocaleString('sk-SK')}</time>{last&&<em className={`pipeline-live-status ${last.status}`}><i className={`status-dot ${last.status}`}/>{active?'BEŽÍ':last.status.toUpperCase()} · RUN #{last.sequence}</em>}</div><div className="pipeline-actions"><button className="button primary" disabled={starting===pipeline.id||!!active} onClick={()=>startPipeline(pipeline)}><Play size={14}/>{active?'Beží':'Spustiť'}</button><button className="icon-button" title="Premenovať pipeline" onClick={()=>{setRenameTarget(pipeline);setRenameValue(pipeline.name)}}><Edit3 size={14}/></button><button className="button ghost" onClick={()=>setEditing(pipeline)}><Settings2 size={14}/>Upraviť</button><button className="icon-button danger" title="Vymazať pipeline" onClick={()=>removePipeline(pipeline)}><Trash2 size={14}/></button></div></article>})}</div>
    {!loading&&!pipelines.length&&<div className="empty-state"><GitBranch size={26}/><h3>Zatiaľ neexistuje žiadna pipeline</h3><p>Nová pipeline sa otvorí ako úplne prázdny graf.</p><button className="button primary" onClick={()=>setEditing(null)}>Vytvoriť pipeline</button></div>}
    {renameTarget&&<div className="modal-backdrop" onMouseDown={()=>setRenameTarget(null)}><form className="modal compact" onSubmit={event=>{event.preventDefault();renamePipeline()}} onMouseDown={event=>event.stopPropagation()}><p className="eyebrow">RENAME PIPELINE</p><h2>Premenovať pipeline</h2><label>Nový názov<input autoFocus value={renameValue} onChange={event=>setRenameValue(event.target.value)} required/></label><div className="modal-actions"><button type="button" className="button ghost" onClick={()=>setRenameTarget(null)}>Zrušiť</button><button className="button primary">Premenovať</button></div></form></div>}
  </div>
}
