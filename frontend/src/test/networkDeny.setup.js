import { installNetworkDeny } from './networkGuard'

// Fail-closed replacement for the global MSW guard on the MSW-free DOM project.
installNetworkDeny(globalThis)
