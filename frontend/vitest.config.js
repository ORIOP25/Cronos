import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const nodeTestFiles = [
  'src/test/activateAndBootstrapOrganization.test.js',
  'src/test/apiClient.test.js',
  'src/test/apiErrors.test.js',
  'src/test/authDesign.test.js',
  'src/test/classDraft.test.js',
  'src/test/clerkRateLimit.test.js',
  'src/test/ContactQuestionnaire.test.jsx',
  'src/test/e2eRuntimeGuards.test.js',
  'src/test/eslintConfig.test.js',
  'src/test/favicon.test.js',
  'src/test/formatUtils.test.js',
  'src/test/foundationModel.test.js',
  'src/test/MarketingResponsiveCss.test.js',
  'src/test/presentation.test.js',
  'src/test/queryKeys.test.js',
  'src/test/roleAccess.test.js',
  'src/test/schoolConfigPayloads.test.js',
  'src/test/securityHeaders.test.js',
  'src/test/simulationEngine.test.js',
  'src/test/terminology.test.js',
  'src/test/tutorialApiAdapter.test.js',
  'src/test/tutorialEngine.test.js',
  'src/test/weekSubmission.test.js',
]

const supportFiles = [
  'src/test/setup.js',
  'src/test/msw.setup.js',
  'src/test/msw/**',
  'src/test/testUtils.jsx',
]

const common = {
  globals: true,
  isolate: true,
  pool: 'threads',
  maxWorkers: 2,
  css: false,
  exclude: ['e2e/**', 'scripts/**', 'node_modules/**', ...supportFiles],
}

export default defineConfig({
  plugins: [react()],
  envDir: false,
  test: {
    reporters: process.env.CI ? ['default', 'junit'] : ['default'],
    outputFile: process.env.CI ? { junit: './test-results/vitest-junit.xml' } : undefined,
    coverage: {
      provider: 'v8',
      reporter: ['lcov', 'text', 'json-summary'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{js,jsx}'],
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
    },
    projects: [
      {
        plugins: [react()],
        test: {
          ...common,
          name: 'node',
          environment: 'node',
          include: nodeTestFiles,
        },
      },
      {
        plugins: [react()],
        test: {
          ...common,
          name: 'dom',
          environment: 'jsdom',
          setupFiles: ['./src/test/setup.js', './src/test/msw.setup.js'],
          exclude: [...common.exclude, ...nodeTestFiles],
          include: ['src/test/**/*.{js,jsx}'],
          deps: {
            optimizer: {
              web: {
                enabled: true,
                include: ['@coreui/react', '@coreui/icons-react'],
              },
            },
          },
        },
      },
    ],
  },
})
