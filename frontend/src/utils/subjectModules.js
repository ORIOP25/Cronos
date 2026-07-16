export const EMPTY_MODULE = Object.freeze({ name: '', code: '', hours_total: '' })

export function normalizeModule(module) {
  const name = module.name?.trim() ?? ''
  const code = module.code?.trim() ?? ''
  const hoursTotal = Number.parseInt(module.hours_total, 10)
  if (!name || !Number.isInteger(hoursTotal) || hoursTotal <= 0) return null
  return {
    ...(module.id == null ? {} : { id: module.id }),
    name,
    code,
    hours_total: hoursTotal,
  }
}
