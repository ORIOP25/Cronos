import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'react-hot-toast'
import AppToaster from '../components/AppToaster'

function stubMatchMedia(initialMatches) {
  const listeners = new Set()
  window.matchMedia = vi.fn((query) => ({
    matches: initialMatches,
    media: query,
    addEventListener: (_event, listener) => listeners.add(listener),
    removeEventListener: (_event, listener) => listeners.delete(listener),
  }))
  return {
    update(matches) {
      listeners.forEach((listener) => listener({ matches }))
    },
  }
}

function getToastWrapper() {
  return document.querySelector('[data-rht-toaster] > div')
}

describe('AppToaster', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    stubMatchMedia(true)
  })

  afterEach(() => {
    act(() => { toast.remove() })
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('expires a success at four active seconds and removes it after the exit delay', () => {
    render(<AppToaster />)
    act(() => { toast.success('Preferências guardadas.') })

    act(() => { vi.advanceTimersByTime(3999) })
    expect(screen.getByText('Preferências guardadas.')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1) })
    expect(screen.getByText('Preferências guardadas.')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1000) })
    expect(screen.queryByText('Preferências guardadas.')).not.toBeInTheDocument()
  })

  it('expires an error at six active seconds and removes it after the exit delay', () => {
    render(<AppToaster />)
    act(() => { toast.error('Não foi possível guardar. Tente novamente.') })

    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível guardar. Tente novamente.')
    act(() => { vi.advanceTimersByTime(5999) })
    expect(screen.getByRole('alert')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1) })
    expect(screen.getByRole('alert')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1000) })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('announces other results politely', () => {
    render(<AppToaster />)
    act(() => { toast.success('Registo removido.') })

    expect(screen.getByRole('status')).toHaveTextContent('Registo removido.')
  })

  it('pauses the countdown while hovered and resumes with the remaining time', () => {
    render(<AppToaster />)
    act(() => { toast.success('Registo removido.') })
    const container = document.querySelector('[data-rht-toaster]')

    act(() => { vi.advanceTimersByTime(3000) })
    fireEvent.mouseEnter(container)
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(screen.getByText('Registo removido.')).toBeInTheDocument()

    fireEvent.mouseLeave(container)
    act(() => { vi.advanceTimersByTime(999) })
    expect(screen.getByText('Registo removido.')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1) })
    expect(screen.getByText('Registo removido.')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(1000) })
    expect(screen.queryByText('Registo removido.')).not.toBeInTheDocument()
  })

  it('uses the top-right corner from 768px and moves to the top centre below that width', () => {
    const media = stubMatchMedia(true)
    render(<AppToaster />)
    act(() => { toast.success('Registo removido.') })

    expect(window.matchMedia).toHaveBeenCalledWith('(min-width: 768px)')
    expect(getToastWrapper()).toHaveStyle({ justifyContent: 'flex-end' })

    act(() => { media.update(false) })
    expect(getToastWrapper()).toHaveStyle({ justifyContent: 'center' })

    act(() => { media.update(true) })
    expect(getToastWrapper()).toHaveStyle({ justifyContent: 'flex-end' })
  })
})
