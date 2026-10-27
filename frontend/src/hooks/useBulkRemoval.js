import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import { useAuth, useOrganization } from '@clerk/react'
import { getApiErrorMessage } from '../utils/apiErrors'
import { useAttemptScope } from './useAttemptScope'

export function useBulkRemoval(items, onDelete) {
  const { userId } = useAuth()
  const { organization } = useOrganization()
  const scope = `${userId ?? 'signed-out'}:${organization?.id ?? 'none'}`
  const [previousScope, setPreviousScope] = useState(scope)
  const [selected, setSelected] = useState([])
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const [failures, setFailures] = useState([])
  const attemptScope = useAttemptScope()
  const generation = useRef(0)
  useEffect(() => () => { generation.current += 1 }, [scope])
  if (previousScope !== scope) {
    setPreviousScope(scope)
    setSelected([])
    setConfirming(false)
    setPending(false)
    setFailures([])
  }
  const available = items.filter((item) => selected.includes(item.id))
  const toggle = (id) => setSelected((previous) => previous.includes(id) ? previous.filter((value) => value !== id) : [...previous, id])
  const toggleAll = () => setSelected(() => available.length === items.length ? [] : items.map((item) => item.id))
  const remove = async () => {
    const attempt = attemptScope.capture()
    const startedGeneration = generation.current
    const isCurrent = () => generation.current === startedGeneration && attemptScope.isCurrent(attempt)
    const failed = []
    const succeeded = []
    setPending(true)
    for (const item of available) {
      if (!isCurrent()) break
      try {
        await onDelete(item.id)
        succeeded.push(item.id)
      } catch (error) {
        failed.push(`${item.name}: ${getApiErrorMessage(error, 'Não foi possível remover. Tente novamente.')}`)
      }
    }
    if (isCurrent()) {
      setSelected((previous) => previous.filter((id) => !succeeded.includes(id)))
      setFailures(failed)
      setConfirming(false)
      setPending(false)
      if (succeeded.length) toast.success(`${succeeded.length} registo(s) removido(s) ou arquivado(s).`)
    }
  }
  return { selected, available, confirming, setConfirming, pending, failures, toggle, toggleAll, remove }
}

