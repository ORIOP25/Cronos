import React, { createContext, useState, useCallback, useRef, useMemo } from 'react'

const ToastContext = createContext(null)

let toastId = 0

/**
 * ToastProvider — sistema de notificações centralizado.
 * Substitui CAlert inline por toasts com auto-dismiss.
 *
 * Uso:
 *   const toast = useToast()
 *   toast.success('Guardado com sucesso')
 *   toast.error('Erro ao guardar')
 *   toast.warning('Atenção: os dados podem estar desatualizados')
 *   toast.info('A processar...')
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef({})

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    if (timersRef.current[id]) {
      clearTimeout(timersRef.current[id])
      delete timersRef.current[id]
    }
  }, [])

  const addToast = useCallback((message, variant = 'info', duration = 4000) => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, variant }])
    if (duration > 0) {
      timersRef.current[id] = setTimeout(() => removeToast(id), duration)
    }
    return id
  }, [removeToast])

  const toast = useCallback((message, variant, duration) => addToast(message, variant, duration), [addToast])

  const api = useMemo(() => ({
    success: (msg, dur) => toast(msg, 'success', dur),
    error: (msg, dur) => toast(msg, 'danger', dur),
    warning: (msg, dur) => toast(msg, 'warning', dur),
    info: (msg, dur) => toast(msg, 'info', dur),
    remove: removeToast,
    toasts,
  }), [toast, removeToast, toasts])

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div className="zen-toast-container">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={`zen-toast zen-toast-${t.variant}`}
              role="alert"
              onClick={() => removeToast(t.id)}
              style={{ cursor: 'pointer' }}
            >
              <span style={{ flex: 1, fontSize: '0.88rem' }}>{t.message}</span>
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  )
}


