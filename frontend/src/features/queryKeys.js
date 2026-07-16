export function orgQueryKey(resource, orgId, ...scope) {
  return [resource, orgId, ...scope]
}

export function invalidateOrgQueries(queryClient, orgId, resources) {
  if (!orgId) return Promise.resolve()

  return Promise.all(resources.map((resource) => queryClient.invalidateQueries({
    queryKey: orgQueryKey(resource, orgId),
  })))
}
