import type { Field } from '~/types/metadata'
import type { Slot } from '~/types/uploads'
import type { TokenInfo } from '~/types/token'
import { formatBytes } from './index'

export function validateSlot(slot: Slot, schema: Field[], tokenInfo: TokenInfo | null): string[] {
  const errs: string[] = []
  if (!slot.file) return errs

  schema.forEach((f) => {
    const val = slot.values[f.key]
    if (f.required && (val === null || val === undefined || val === '' || (Array.isArray(val) && !val.length))) {
      errs.push(`${f.label} is required`)
      return
    }
    if (f.type === 'date' && val) {
      if (typeof val === 'string' || typeof val === 'number' || val instanceof Date) {
        const d = new Date(val)
        if (Number.isNaN(d.getTime())) errs.push(`${f.label} must be a valid date`)
      }
    }
    if (f.type === 'number' || f.type === 'integer') {
      if (val !== null && val !== undefined && val !== '') {
        const num = Number(val)
        if (Number.isNaN(num)) errs.push(`${f.label} must be numeric`)
        if (f.min !== undefined && num < f.min) errs.push(`${f.label} must be >= ${f.min}`)
        if (f.max !== undefined && num > f.max) errs.push(`${f.label} must be <= ${f.max}`)
      }
    }
    if ((f.type === 'string' || f.type === 'text') && typeof val === 'string') {
      if (f.minLength && val.length < f.minLength) errs.push(`${f.label} must be at least ${f.minLength} chars`)
      if (f.maxLength && val.length > f.maxLength) errs.push(`${f.label} must be at most ${f.maxLength} chars`)
    }
    if (f.type === 'select' && f.options && val && typeof val === 'string') {
      if (!f.allowCustom) {
        const opts = f.options.map((o) => (typeof o === 'string' ? o : o.value))
        if (!opts.includes(val)) errs.push(`${f.label} has invalid option`)
      }
    }
    if (f.type === 'multiselect' && Array.isArray(val) && f.options) {
      if (!f.allowCustom) {
        const opts = f.options.map((o) => (typeof o === 'string' ? o : o.value))
        val.forEach((v: unknown) => {
          if (typeof v === 'string' && !opts.includes(v)) errs.push(`${f.label} has invalid option: ${v}`)
        })
      }
    }
    if (f.type === 'multiselect' && f.allowCustom && typeof val === 'string') {
      slot.values[f.key] = val
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean)
    }
    if (f.regex && typeof val === 'string' && val !== '') {
      try {
        const re = new RegExp(f.regex)
        if (!re.test(val)) errs.push(`${f.label} has invalid format`)
      } catch {
        // ignore bad regex
      }
    }
  })

  if (tokenInfo?.max_size_bytes && slot.file && slot.file.size > tokenInfo.max_size_bytes) {
    errs.push(
      `The selected file exceeds max size '${formatBytes(tokenInfo.max_size_bytes)}'. Current file size is '${formatBytes(slot.file.size)}'.`
    )
  }

  slot.errors = errs
  return errs
}
