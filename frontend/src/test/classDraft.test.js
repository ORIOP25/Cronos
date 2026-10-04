// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { createClassDraft, validateClassDraft } from '../utils/classDraft'

describe('class drafts', () => {
  it('creates defaults and preserves edit values', () => {
    expect(createClassDraft({}, 2026)).toEqual({
      name: '', size: 25, grade_level: 10, start_year: 2026, end_year: 2029,
    })
    expect(createClassDraft({ name: '11 A', size: 30 }, 2026)).toEqual({
      name: '11 A', size: 30, grade_level: 10, start_year: 2026, end_year: 2029,
    })
  })

  it.each([
    [{ name: ' ', size: 25, grade_level: 10, start_year: 2026, end_year: 2029 }, /nome/i, 'name'],
    [{ name: 'A', size: 0, grade_level: 10, start_year: 2026, end_year: 2029 }, /alunos/i, 'size'],
    [{ name: 'A', size: 25, grade_level: 9, start_year: 2026, end_year: 2029 }, /ano/i, 'grade_level'],
    [{ name: 'A', size: 25, grade_level: 10, start_year: 1999, end_year: 2029 }, /início/i, 'start_year'],
    [{ name: 'A', size: 25, grade_level: 10, start_year: 2029, end_year: 2029 }, /posterior/i, 'date_range'],
  ])('rejects invalid domain values and names the affected field', (draft, message, field) => {
    const result = validateClassDraft(draft)
    expect(result.error).toMatch(message)
    expect(result.field).toBe(field)
  })

  it('normalizes numbers and rejects duplicate names case-insensitively', () => {
    const draft = { name: ' 10 A ', size: '28', grade_level: '10', start_year: '2026', end_year: '2029' }
    expect(validateClassDraft(draft).value).toEqual({
      name: '10 A', size: 28, grade_level: 10, start_year: 2026, end_year: 2029,
    })
    const duplicate = validateClassDraft(draft, [{ name: '10 a' }])
    expect(duplicate.error).toMatch(/já foi adicionada/i)
    expect(duplicate.field).toBe('name')
  })
})
