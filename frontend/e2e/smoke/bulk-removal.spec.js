import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { goTo, loginAsAdminReal } from '../utils/clerk-helpers.js'
import { apiRequest, getNormalRoomTypeId } from '../utils/scheduler-fixtures.js'

test.use({ storageState: '.auth/admin.json' })

test('removes selected subjects with one confirmation', async ({ page }, testInfo) => {
  await loginAsAdminReal(page)
  await goTo(page, '/dashboard')
  const roomType = await getNormalRoomTypeId(page)
  const suffix = Date.now()
  const names = [`Bulk A ${suffix}`, `Bulk B ${suffix}`, `Bulk C ${suffix}`]
  const created = []
  try {
    for (const name of names) created.push(await apiRequest(page, 'POST', '/subjects/', { name, room_type_id: roomType, modules: [] }))
    await goTo(page, '/subjects')
    await expect(page.getByRole('button', { name: /remover selecionados/i })).toHaveCount(0)
    await page.getByRole('checkbox', { name: `Selecionar ${names[0]}` }).check()
    await page.getByRole('checkbox', { name: `Selecionar ${names[1]}` }).check()
    const toolbar = page.getByRole('region', { name: 'Ações da seleção' })
    await expect(toolbar.getByRole('status')).toHaveText('2 selecionados')
    await toolbar.getByRole('button', { name: 'Limpar seleção' }).click()
    await expect(page.getByRole('checkbox', { name: 'Selecionar todos', exact: true })).toBeFocused()
    await expect(page.getByRole('checkbox', { name: `Selecionar ${names[0]}` })).not.toBeChecked()
    await page.getByRole('checkbox', { name: `Selecionar ${names[0]}` }).check()
    await page.getByRole('checkbox', { name: `Selecionar ${names[1]}` }).check()
    for (const width of [375, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 })
      await expect(page.getByRole('checkbox', { name: 'Selecionar todos', exact: true })).toBeVisible()
      await expect(toolbar).toBeInViewport()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: testInfo.outputPath(`bulk-selection-${width}.png`), fullPage: true })
      await toolbar.getByRole('button', { name: /remover selecionados/i }).click()
      const dialog = page.getByRole('dialog', { name: 'Remover selecionados', exact: true })
      await expect(dialog).toHaveCSS('opacity', '1')
      await expect(dialog.getByRole('list', { name: 'Registos selecionados' }).getByRole('listitem')).toHaveCount(2)
      await expect(dialog.getByRole('button', { name: 'Cancelar', exact: true })).toHaveClass(/btn-outline-secondary/)
      await expect(dialog.getByRole('button', { name: 'Remover', exact: true })).toHaveCSS('background-color', 'rgb(143, 45, 11)')
      await page.screenshot({ path: testInfo.outputPath(`bulk-confirmation-${width}.png`), fullPage: true })
      if (width === 1440) {
        const accessibility = await new AxeBuilder({ page }).include('.confirmation-modal').withTags(['wcag2a', 'wcag2aa']).analyze()
        expect(accessibility.violations).toEqual([])
      }
      await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(page.getByRole('checkbox', { name: `Selecionar ${names[0]}` })).toBeChecked()
    }
    await page.getByRole('button', { name: /remover selecionados/i }).click()
    await page.getByRole('button', { name: 'Remover', exact: true }).click()
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
