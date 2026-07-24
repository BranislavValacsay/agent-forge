import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { en, sk, type MessageKey } from './catalogs'

export type Locale = 'sk' | 'en'
export type MessageParams = Record<string, unknown>

const catalogs = { en, sk } as const
const storageKey = 'agent-forge:locale'
let activeLocale: Locale = normalizeLocale(localStorage.getItem(storageKey) ?? navigator.language)

function normalizeLocale(value?: string | null): Locale {
  return value?.toLowerCase().startsWith('en') ? 'en' : 'sk'
}

function interpolate(message: string, params: MessageParams = {}): string {
  return message.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? `{${name}}`))
}

export function translate(key: MessageKey | string, params: MessageParams = {}, locale = activeLocale): string {
  const catalog = catalogs[locale] as Record<string, string>
  const fallback = en as Record<string, string>
  return interpolate(catalog[key] ?? fallback[key] ?? key, params)
}

export function currentLocale(): Locale {
  return activeLocale
}

export function localeTag(locale = activeLocale): string {
  return locale === 'sk' ? 'sk-SK' : 'en-US'
}

export function translateStatus(status: string): string {
  return translate(`status.${status}`)
}

export function translateTrigger(trigger: string): string {
  return translate(`trigger.${trigger}`)
}

export function translateVisibility(visibility: string): string {
  return translate(`visibility.${visibility}`)
}

type I18nValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: typeof translate
  dateTime: (value: string | Date) => string
  time: (value: string | Date) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(activeLocale)
  function setLocale(locale: Locale) {
    activeLocale = locale
    localStorage.setItem(storageKey, locale)
    document.documentElement.lang = locale
    setLocaleState(locale)
  }
  useEffect(() => {
    activeLocale = locale
    document.documentElement.lang = locale
  }, [locale])
  const value = useMemo<I18nValue>(() => ({
    locale,
    setLocale,
    t: (key, params = {}) => translate(key, params, locale),
    dateTime: value => new Intl.DateTimeFormat(localeTag(locale), { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)),
    time: value => new Intl.DateTimeFormat(localeTag(locale), { timeStyle: 'medium' }).format(new Date(value)),
  }), [locale])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside I18nProvider')
  return value
}

export function applyAccountLocale(locale?: string | null): Locale {
  const next = normalizeLocale(locale)
  activeLocale = next
  localStorage.setItem(storageKey, next)
  document.documentElement.lang = next
  window.dispatchEvent(new CustomEvent<Locale>('agent-forge:locale', { detail: next }))
  return next
}
