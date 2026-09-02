import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'playwright-report', 'test-results']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      react.configs.flat.recommended,
      react.configs.flat['jsx-runtime'],
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      'no-unused-vars': ['error', {
        varsIgnorePattern: '^_',
        argsIgnorePattern: '^_',
      }],
      'react/prop-types': 'off',
      'react/jsx-no-undef': 'error',
    },
  },
  {
    files: ['e2e/**/*.js', 'playwright.config.js'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  {
    files: ['src/pages/**/*.{js,jsx}', 'src/components/**/*.{js,jsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        paths: [{
          name: '@tanstack/react-query',
          importNames: ['useQuery', 'useMutation', 'useQueryClient'],
          message: 'Pages and components must compose feature data hooks.',
        }],
        patterns: [{
          group: ['**/apiClient'],
          message: 'HTTP access belongs in a feature data module.',
        }],
      }],
    },
  },
])
