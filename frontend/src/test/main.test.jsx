import { describe, it, expect, beforeEach, vi } from 'vitest'

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

  it('delivers the local authentication routes to ClerkProvider', async () => {
    await import('../main.jsx')

    const clerkProvider = reactDom.rendered.props.children
    expect(clerkProvider.props.signInUrl).toBe('/login')
    expect(clerkProvider.props.signUpUrl).toBe('/register')
    expect(clerkProvider.props.taskUrls).toEqual({
      'choose-organization': '/login/tasks/choose-organization',
    })
  }, 15_000)
})
