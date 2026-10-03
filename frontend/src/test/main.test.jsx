import { Children } from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import AppToaster from '../components/AppToaster'

const reactDom = vi.hoisted(() => ({ rendered: null }))

vi.mock('react-dom/client', () => {
  const createRoot = () => ({
    render: (element) => {
      reactDom.rendered = element
    },
  })
  return {
    createRoot,
    default: { createRoot },
  }
})

describe('frontend authentication composition', () => {
  beforeEach(() => {
    reactDom.rendered = null
  })

  it('delivers the local authentication routes to ClerkProvider and mounts one feedback host', async () => {
    await import('../main.jsx')

    const clerkProvider = reactDom.rendered.props.children
    expect(clerkProvider.props.signInUrl).toBe('/login')
    expect(clerkProvider.props.signUpUrl).toBe('/register')
    expect(clerkProvider.props.taskUrls).toEqual({
      'choose-organization': '/login/tasks/choose-organization',
    })

    const userQueryProvider = clerkProvider.props.children.props.children
    const feedbackHosts = Children.toArray(userQueryProvider.props.children).filter((child) => child.type === AppToaster)
    expect(feedbackHosts).toHaveLength(1)
  }, 15_000)
})
