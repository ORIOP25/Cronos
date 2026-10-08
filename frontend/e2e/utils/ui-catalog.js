import { expect } from '@playwright/test'
import { readSchoolResource } from './ui-school.js'

async function submit(page, button, path, method) {
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/${path}` && response.request().method() === method)
  await button.click()
  const response = await saved
  expect(response.status()).toBe(200)
  return response.json()
}

async function remove(page, button, path, confirmText = 'Confirmar') {
  await button.click()
  const result = await submit(page, page.getByRole('dialog').getByRole('button', { name: confirmText, exact: true }), path, 'DELETE')
  expect(result.remove_effect).toBe('hard_delete')
  await expect(page.getByRole('dialog')).toHaveCount(0)
}

export async function exerciseRoomCrud(page, runId) {
  const name = `Sala Aceitação ${runId}`
  await page.goto('/rooms')
  await page.getByRole('button', { name: 'Nova Sala', exact: true }).click()
  await page.getByLabel('Nome da Sala', { exact: true }).fill(name)
  await page.getByLabel('Lotação', { exact: true }).fill('30')
  await page.getByLabel('Tipo de Sala', { exact: true }).selectOption('lab')
  const created = await submit(page, page.getByRole('button', { name: 'Criar Sala', exact: true }), 'rooms/', 'POST')
  await page.reload()
  expect((await readSchoolResource(page, 'rooms/')).find(row => row.id === created.id)).toMatchObject({ name, capacity: 30, type: 'lab' })
  await page.getByRole('button', { name: `Editar ${name}`, exact: true }).click()
  await page.getByLabel('Nome da Sala', { exact: true }).fill(`${name} revista`)
  await page.getByLabel('Lotação', { exact: true }).fill('34')
  const updated = await submit(page, page.getByRole('button', { name: 'Atualizar Sala', exact: true }), `rooms/${created.id}`, 'PATCH')
  expect(updated.id).toBe(created.id)
  await page.reload()
  expect((await readSchoolResource(page, 'rooms/')).find(row => row.id === created.id)).toMatchObject({ name: `${name} revista`, capacity: 34, type: 'lab' })
  await remove(page, page.getByRole('button', { name: `Remover ${name} revista`, exact: true }), `rooms/${created.id}`)
  await page.reload()
  expect((await readSchoolResource(page, 'rooms/')).some(row => row.id === created.id)).toBe(false)
}

export async function exerciseSubjectCrud(page, runId) {
  const name = `Disciplina Aceitação ${runId}`
  await page.goto('/subjects')
  await page.getByRole('button', { name: 'Nova Disciplina', exact: true }).click()
  await page.getByLabel('Nome da Disciplina', { exact: true }).fill(name)
  await page.getByLabel('Sala Preferencial', { exact: true }).selectOption('normal')
  await page.getByLabel('Nome do módulo', { exact: true }).fill('Módulo inicial')
  await page.getByLabel('Código UFCD', { exact: true }).fill('QA-01')
  await page.getByLabel('Horas', { exact: true }).fill('7')
  await page.getByRole('button', { name: 'Adicionar', exact: true }).click()
  const created = await submit(page, page.getByRole('button', { name: 'Guardar Disciplina', exact: true }), 'subjects/', 'POST')
  expect(created.modules).toHaveLength(1)
  await page.reload()
  await page.getByRole('button', { name: `Editar ${name}`, exact: true }).click()
  await page.getByRole('button', { name: 'Editar Módulo inicial', exact: true }).click()
  await page.getByLabel('Nome do módulo', { exact: true }).fill('Módulo revisto')
  await page.getByLabel('Horas', { exact: true }).fill('8')
  await page.getByRole('button', { name: 'Guardar', exact: true }).click()
  await page.getByLabel('Nome da Disciplina', { exact: true }).fill(`${name} revista`)
  const updated = await submit(page, page.getByRole('button', { name: 'Guardar Disciplina', exact: true }), `subjects/${created.id}`, 'PATCH')
  expect(updated.id).toBe(created.id)
  expect(updated.modules[0]).toMatchObject({ id: created.modules[0].id, name: 'Módulo revisto', code: 'QA-01', hours_total: 8, order: 0 })
  await page.reload()
  const persisted = (await readSchoolResource(page, 'subjects/')).find(row => row.id === created.id)
  expect(persisted.name).toBe(`${name} revista`)
  expect(persisted.modules).toEqual(updated.modules)
  await remove(page, page.getByRole('button', { name: `Remover ${name} revista`, exact: true }), `subjects/${created.id}`)
  await page.reload()
  expect((await readSchoolResource(page, 'subjects/')).some(row => row.id === created.id)).toBe(false)
}

export async function exerciseCourseAndInitialClass(page, runId, year) {
  const name = `Curso Aceitação ${runId}`, className = 'Aceitação 10', abbreviation = `QA${runId.slice(-6).toUpperCase()}`
  await page.goto('/courses')
  await page.getByRole('button', { name: 'Novo Curso', exact: true }).click()
  for (const [id, value] of Object.entries({ 'course-name': name, 'course-abbreviation': abbreviation, 'course-class-name': className, 'course-class-size': '27', 'course-class-grade': '10', 'course-class-start': String(year), 'course-class-end': String(year + 3) })) await page.locator(`#${id}`).fill(value)
  // Submit the filled initial class directly; never click "Adicionar turma".
  const created = await submit(page, page.getByRole('button', { name: 'Criar Curso', exact: true }), 'courses/', 'POST')
  expect(created.classes).toHaveLength(1)
  expect(created.classes[0]).toMatchObject({ name: className, size: 27, grade_level: 10, start_year: year, end_year: year + 3 })
  const classId = created.classes[0].id
  await page.reload()
  await page.getByText(name, { exact: true }).click()
  await expect(page.getByRole('button', { name: `Abrir turma ${className}`, exact: true })).toBeVisible()
  expect((await readSchoolResource(page, `courses/${created.id}`)).classes).toEqual(created.classes)
  await page.getByRole('button', { name: 'Editar', exact: true }).click()
  await page.getByLabel('Nome do Curso', { exact: true }).fill(`${name} revisto`)
  await submit(page, page.getByRole('button', { name: 'Guardar', exact: true }), `courses/${created.id}`, 'PATCH')
  await page.getByRole('button', { name: `Editar ${className}`, exact: true }).click()
  await page.getByLabel('Nº Alunos', { exact: true }).fill('31')
  const updated = await submit(page, page.getByRole('dialog').getByRole('button', { name: /Atualizar|Guardar/ }), `courses/${created.id}/classes/${classId}`, 'PATCH')
  expect(updated.id).toBe(classId)
  await page.reload()
  const persisted = await readSchoolResource(page, `courses/${created.id}`)
  expect(persisted.name).toBe(`${name} revisto`)
  expect(persisted.classes[0]).toMatchObject({ id: classId, size: 31, name: className })
  await remove(page, page.getByRole('button', { name: `Remover ${className}`, exact: true }), `courses/${created.id}/classes/${classId}`, 'Remover')
  await remove(page, page.getByRole('button', { name: 'Apagar curso', exact: true }), `courses/${created.id}`, 'Remover')
  await expect(page).toHaveURL(/\/courses$/)
  await page.reload()
  expect((await readSchoolResource(page, 'courses/?limit=1000')).some(row => row.id === created.id)).toBe(false)
  expect((await readSchoolResource(page, 'classes/')).some(row => row.id === classId)).toBe(false)
}
