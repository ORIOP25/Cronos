import { useEffect, useMemo } from 'react'
import { useAuth } from '@clerk/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createQueryClient } from './queryClient'

export function UserQueryProvider({ children }) {
  const { userId } = useAuth({ treatPendingAsSignedOut: false })
  const queryClient = useMemo(() => createQueryClient(userId), [userId])

  useEffect(() => () => queryClient.clear(), [queryClient])

  return (
    <QueryClientProvider key={userId ?? 'signed-out'} client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}
