import { expect, test } from '@playwright/test'
import { goTo, loginAsAdminReal } from '../utils/clerk-helpers.js'
import { apiRequest, getNormalRoomTypeId } from '../utils/scheduler-fixtures.js'

test.use({ storageState: '.auth/admin.json' })

test('removes selected subjects with one confirmation', async ({ page }) => {
  await loginAsAdminReal(page)
  await goTo(page, '/dashboard')
  const roomType = await getNormalRoomTypeId(page)
  const suffix = Date.now()
  const names = [`Bulk A ${suffix}`, `Bulk B ${suffix}`, `Bulk C ${suffix}`]
  const created = []
  try {
    for (const name of names) created.push(await apiRequest(page, 'POST', '/subjects/', { name, room_type_id: roomType, modules: [] }))
    await goTo(page, '/subjects')
    await page.getByRole('checkbox', { name: `Selecionar ${names[0]}` }).check()
    await page.getByRole('checkbox', { name: `Selecionar ${names[1]}` }).check()
    await page.getByRole('button', { name: /remover selecionados/i }).click()
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click()
    await expect(page.getByText(names[0], { exact: true })).toHaveCount(0)
    await expect(page.getByText(names[1], { exact: true })).toHaveCount(0)
    await expect(page.getByText(names[2], { exact: true })).toBeVisible()
  } finally {
    const remaining = await apiRequest(page, 'GET', '/subjects/')
    for (const subject of remaining.filter((item) => created.some((createdItem) => createdItem.id === item.id))) {
      await apiRequest(page, 'DELETE', `/subjects/${subject.id}`)
    }
  }
})
