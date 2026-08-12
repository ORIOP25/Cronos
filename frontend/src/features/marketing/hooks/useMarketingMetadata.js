import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { marketingMetadata } from '../content/metadata'

function setAttribute(selector, attribute, value) {
  const element = document.querySelector(selector)
  if (!element) throw new Error(`Missing metadata element: ${selector}`)
  element.setAttribute(attribute, value)
}

function applyMetadata(metadata) {
  document.title = metadata.title
  setAttribute('meta[name="description"]', 'content', metadata.description)
  setAttribute('link[rel="canonical"]', 'href', metadata.canonicalUrl)
  setAttribute('meta[property="og:title"]', 'content', metadata.title)
  setAttribute('meta[property="og:description"]', 'content', metadata.description)
  setAttribute('meta[property="og:url"]', 'content', metadata.canonicalUrl)
  setAttribute('meta[name="twitter:title"]', 'content', metadata.title)
  setAttribute('meta[name="twitter:description"]', 'content', metadata.description)
}

export function useMarketingMetadata() {
  const { pathname } = useLocation()

  useEffect(() => {
    const metadata = marketingMetadata[pathname]
    if (!metadata) {
      if (import.meta.env.DEV) throw new Error(`Missing marketing metadata for public route: ${pathname}`)
      return
    }

    applyMetadata(metadata)
    return () => applyMetadata(marketingMetadata['/'])
  }, [pathname])
}
