export const PUBLIC_ASSET_REVISION = '20260920'

export function publicAsset(pathname) {
  return `${pathname}?v=${PUBLIC_ASSET_REVISION}`
}
