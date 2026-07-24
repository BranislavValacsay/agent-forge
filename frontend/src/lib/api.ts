import { currentLocale, translate } from '../i18n'

const base = import.meta.env.VITE_API_URL ?? '/api/v1'

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public params?: Record<string, unknown>) {
    super(message)
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'Accept-Language': currentLocale(), ...init.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = body.detail
    const code = typeof detail === 'object' && detail ? detail.code : body.code
    const params = (typeof detail === 'object' && detail ? detail.params : body.params) ?? {}
    const fallback = typeof detail === 'string' ? detail : detail?.message
    throw new ApiError(response.status, code ? translate(`api.${code}`, params) : fallback ?? translate('errors.requestFailed'), code, params)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
