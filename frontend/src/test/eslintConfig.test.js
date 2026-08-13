// @vitest-environment node
import process from 'node:process'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const frontendRoot = process.cwd()

async function lint(source, filePath = 'src/lint-fixture.jsx') {
  const eslint = new ESLint({ cwd: frontendRoot })
  const [result] = await eslint.lintText(source, { filePath })
  return result
}

describe('ESLint unused bindings', () => {
  it('rejects unused PascalCase identifiers and allows underscore prefixes', async () => {
    const result = await lint('const UnusedValue = 1\nconst _unused = 1\n')

    expect(result.messages).toEqual([
      expect.objectContaining({ ruleId: 'no-unused-vars', severity: 2 }),
    ])
  }, 30_000)
})

describe('ESLint data ownership boundary', () => {
  it('rejects API and React Query primitives in pages and components', async () => {
    const result = await lint(
      "import apiClient from '../apiClient'\nimport { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'\nvoid apiClient\nvoid useQuery\nvoid useMutation\nvoid useQueryClient\n",
      'src/pages/lint-fixture.jsx',
    )

    expect(result.messages.filter(({ ruleId }) => ruleId === 'no-restricted-imports')).toHaveLength(4)
  }, 30_000)
})
