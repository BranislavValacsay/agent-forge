export type PortType = 'string' | 'json' | 'number' | 'boolean' | 'file' | 'image' | 'any'

export interface PortDefinition {
  name: string
  type: PortType
  description?: string
  required?: boolean
}

export interface ContractSchema {
  type: 'object'
  properties: Record<string, {
    type?: string
    description?: string
    format?: string
    contentMediaType?: string
    'x-agentforge-type'?: PortType
  }>
  required: string[]
}

export interface ValueMapping {
  source: string
  target: string
  sourceType: PortType
  targetType: PortType
}

export function portsToSchema(ports: PortDefinition[]): ContractSchema {
  const properties: ContractSchema['properties'] = {}
  for (const port of ports) {
    const base = { description: port.description, 'x-agentforge-type': port.type }
    if (port.type === 'json') properties[port.name] = { ...base, type: 'object' }
    else if (port.type === 'file') properties[port.name] = { ...base, type: 'string', format: 'binary', contentMediaType: 'application/octet-stream' }
    else if (port.type === 'image') properties[port.name] = { ...base, type: 'string', format: 'binary', contentMediaType: 'image/*' }
    else if (port.type === 'any') properties[port.name] = base
    else properties[port.name] = { ...base, type: port.type }
  }
  return { type: 'object', properties, required: ports.filter(port => port.required).map(port => port.name) }
}

export function schemaToPorts(schema: Record<string, unknown>): PortDefinition[] {
  const properties = (schema.properties ?? {}) as ContractSchema['properties']
  const required = new Set(Array.isArray(schema.required) ? schema.required as string[] : [])
  return Object.entries(properties).map(([name, property]) => ({
    name,
    type: property['x-agentforge-type'] ?? inferType(property),
    description: property.description,
    required: required.has(name),
  }))
}

function inferType(property: ContractSchema['properties'][string]): PortType {
  if (property.contentMediaType?.startsWith('image/')) return 'image'
  if (property.format === 'binary') return 'file'
  if (property.type === 'object' || property.type === 'array') return 'json'
  if (property.type === 'string' || property.type === 'number' || property.type === 'boolean') return property.type
  return 'any'
}

export function compatible(source: PortType, target: PortType): boolean {
  return source === target || source === 'any' || target === 'any'
}
