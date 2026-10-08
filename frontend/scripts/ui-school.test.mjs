import assert from 'node:assert/strict'
import test from 'node:test'
import { futureSchoolPeriod, readOriginalExpectations } from '../e2e/utils/ui-school.js'

test('campaign school starts after its actual Lisbon creation day with a full future horizon', () => {
  assert.deepEqual(futureSchoolPeriod(new Date('2026-10-07T17:00:00Z')), {
    start: '2026-10-08', preferred: '2027-07-05', hard: '2027-10-08',
  })
  assert.equal(futureSchoolPeriod(new Date('2026-03-29T23:30:00Z')).start, '2026-03-31')
  assert.throws(() => futureSchoolPeriod(new Date('invalid')))
})

test('native original-data inspection preserves UTF-8 labels and reads all five full resources', async () => {
  const original = await readOriginalExpectations()
  assert.equal(original.subjects['Português'].modules[0].name, 'Fundamentos')
  assert.equal(original.classes[0].grade_level, 10)
  assert.equal(original.classes[0].start_year, 2026)
  assert.equal(original.counts.assignments, 336)
  assert.equal(Object.keys(original.teachers).length, 40)
})
