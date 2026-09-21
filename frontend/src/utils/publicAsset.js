export const PUBLIC_ASSET_REVISION = '20260921'

export function publicAsset(pathname) {
  return `${pathname}?v=${PUBLIC_ASSET_REVISION}`
}
