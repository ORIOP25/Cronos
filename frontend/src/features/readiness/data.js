export function invalidatePreparationQueries(queryClient, orgId) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ['dashboard', orgId] }),
    queryClient.invalidateQueries({ queryKey: ['readiness-bases', orgId] }),
  ])
}
