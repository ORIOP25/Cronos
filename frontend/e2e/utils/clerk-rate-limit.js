export async function observeClerkSignIn(operation) {
  try {
    await operation()
    return true
  } catch (error) {
    if (error?.message?.includes('Too Many Requests')) {
      return false
    }
    throw error
  }
}
