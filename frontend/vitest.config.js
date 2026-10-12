import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import process from 'node:process'
import {
  criticalCoverageInclude,
  criticalDomTests,
  criticalGuardTest,
  criticalNetworkTests,
  criticalNodeTests,
} from './src/test/criticalSelection.js'

const nodeTestFiles = [
  'src/test/apiClient.test.js',
  'src/test/apiErrors.test.js',
  'src/test/authDesign.test.js',
  'src/test/classDraft.test.js',
  'src/test/clerkRateLimit.test.js',
  'src/test/ContactQuestionnaire.test.jsx',
  'src/test/e2eClerkSessionReuse.test.js',
  'src/test/e2eRuntimeGuards.test.js',
  'src/test/eslintConfig.test.js',
  'src/test/favicon.test.js',
  'src/test/formatUtils.test.js',
  'src/test/foundationModel.test.js',
  'src/test/internshipDays.test.js',
  'src/test/criticalSelection.test.js',
  'src/test/queryKeys.test.js',
  'src/test/roleAccess.test.js',
  'src/test/schoolConfigPayloads.test.js',
  'src/test/securityHeaders.test.js',
  'src/test/simulationEngine.test.js',
  'src/test/terminology.test.js',
  'src/test/timeOfDay.test.js',
  'src/test/tutorialApiAdapter.test.js',
  'src/test/tutorialEngine.test.js',
  'src/test/vitePreloadRecovery.test.js',
  'src/test/weekSubmission.test.js',
]

const supportFiles = [
  'src/test/streams.setup.js',
  'src/test/setup.js',
  'src/test/networkGuard.js',
  'src/test/networkDeny.setup.js',
  'src/test/criticalSelection.js',
  'src/test/msw.setup.js',
  'src/test/msw/**',
  'src/test/testUtils.jsx',
]

// Tests that exercise the real data layer close to the network boundary keep the
// fail-closed MSW guard. Every other DOM test uses vi.mock and does not pay for it.
const networkTestFiles = [
  'src/test/featureDataHooks.test.jsx',
  'src/test/schoolConfigData.test.jsx',
]

const common = {
  globals: true,
  isolate: true,
  pool: 'threads',
  maxWorkers: process.env.CI ? 4 : 6,
  css: false,
  exclude: ['e2e/**', 'scripts/**', 'node_modules/**', ...supportFiles],
}

const coreUiOptimizer = {
  optimizer: {
    client: {
      enabled: true,
      include: [
        '@coreui/react',
        '@coreui/icons-react',
        '@coreui/icons',
      ],
    },
  },
}

export default defineConfig(({ mode }) => {
  const critical = mode === 'critical'

  const coverage = {
    provider: 'v8',
    reporter: ['lcov', 'text', 'json-summary'],
    reportsDirectory: './coverage',
    // Critical mode measures the explicit critical source set with the same
    // 45/40/35/45 floors; full mode keeps the whole-app include.
    include: critical ? criticalCoverageInclude : ['src/**/*.{js,jsx}'],
    thresholds: {
      statements: 45,
      branches: 40,
      functions: 35,
      lines: 45,
    },
    exclude: [
      'src/test/**',
      'src/main.jsx',
      'src/assets/**',
    ],
  }

  const fullProjects = [
    {
      test: {
        ...common,
        name: 'node',
        environment: 'node',
        include: nodeTestFiles,
      },
    },
    {
      test: {
        ...common,
        name: 'dom',
        environment: 'jsdom',
        pool: 'threads',
        setupFiles: [
          './src/test/streams.setup.js',
          './src/test/setup.js',
          './src/test/networkDeny.setup.js',
        ],
        exclude: [...common.exclude, ...nodeTestFiles, ...networkTestFiles],
        include: ['src/test/**/*.{js,jsx}'],
        deps: coreUiOptimizer,
      },
    },
    {
      test: {
        ...common,
        name: 'dom-network',
        environment: 'jsdom',
        pool: 'threads',
        setupFiles: [
          './src/test/streams.setup.js',
          './src/test/setup.js',
          './src/test/msw.setup.js',
        ],
        exclude: [...common.exclude],
        include: networkTestFiles,
      },
    },
  ]

  const criticalProjects = [
    {
      test: {
        ...common,
        name: 'node',
        environment: 'node',
        include: [...criticalNodeTests, criticalGuardTest],
      },
    },
    {
      test: {
        ...common,
        name: 'dom',
        environment: 'jsdom',
        pool: 'threads',
        setupFiles: [
          './src/test/streams.setup.js',
          './src/test/setup.js',
          './src/test/networkDeny.setup.js',
        ],
        exclude: [...common.exclude],
        include: criticalDomTests,
        deps: coreUiOptimizer,
      },
    },
    {
      test: {
        ...common,
        name: 'dom-network',
        environment: 'jsdom',
        pool: 'threads',
        setupFiles: [
          './src/test/streams.setup.js',
          './src/test/setup.js',
          './src/test/msw.setup.js',
        ],
        exclude: [...common.exclude],
        include: criticalNetworkTests,
      },
    },
  ]

  return {
    plugins: [react()],
    envDir: false,
    test: {
      sequence: { setupFiles: 'list' },
      reporters: process.env.CI || process.env.VITEST_JUNIT_OUTPUT_FILE
        ? ['default', 'junit']
        : ['default'],
      outputFile: process.env.CI || process.env.VITEST_JUNIT_OUTPUT_FILE
        ? { junit: process.env.VITEST_JUNIT_OUTPUT_FILE || './test-results/vitest-junit.xml' }
        : undefined,
      coverage,
      projects: critical ? criticalProjects : fullProjects,
    },
  }
})
