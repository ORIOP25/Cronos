import { expect, test } from '@playwright/test'
import {
  attachRuntimeGuards,
  expectNoAppCrash,
  goTo,
  loginAsAdminReal,
} from '../utils/clerk-helpers.js'

test.describe.configure({ mode: 'serial' })

test.describe('Tutorial — deterministic local scenario', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('cronos:tutorial:')) localStorage.removeItem(key)
      }
    })
    await loginAsAdminReal(page)
    await page.waitForLoadState('networkidle')
    attachRuntimeGuards(page)
  })

  test('completes all 24 checkpoints through their real controls without skips', async ({ page }) => {
    test.setTimeout(120_000)
    const expectStep = async (number) => {
      await expect(page.getByTestId('tutorial-step-counter')).toHaveText(`Passo ${number} de 24`)
      await expectNoAppCrash(page)
    }

    await goTo(page, '/guide')
    await expect(page.getByTestId('tutorial-workspace')).toBeVisible()
    await expectStep(1)

    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(2)

    await page.getByRole('button', { name: /nova disciplina/i }).click()
    let dialog = page.getByRole('dialog')
    await dialog.getByLabel(/nome da disciplina/i).fill('Sistemas Embebidos')
    await dialog.getByRole('button', { name: /guardar disciplina/i }).click()
    await expectStep(3)

    await page.getByRole('button', { name: /nova disciplina/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/nome da disciplina/i).fill('Automação Industrial')
    await dialog.getByLabel(/nome do módulo/i).fill('UFCD 5412')
    await dialog.getByLabel(/código ufcd/i).fill('5412')
    await dialog.getByLabel(/^horas$/i).fill('25')
    await dialog.getByRole('button', { name: /^adicionar$/i }).click()
    await dialog.getByRole('button', { name: /guardar disciplina/i }).click()
    await expectStep(4)

    await page.getByRole('button', { name: /novo curso/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/nome do curso/i).fill('Técnico de Eletrónica')
    await dialog.getByLabel(/sigla/i).fill('TE')
    await dialog.getByRole('button', { name: /criar curso/i }).click()
    await expectStep(5)

    await page.getByRole('button', { name: /novo curso/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/nome do curso/i).fill('Técnico de Mecatrónica')
    await dialog.getByLabel(/sigla/i).fill('TM')
    await dialog.getByLabel(/nome turma/i).fill('10.º TM')
    await dialog.getByRole('button', { name: /adicionar turma/i }).click()
    await dialog.getByRole('button', { name: /criar curso/i }).click()
    await expectStep(6)

    await page.getByRole('button', { name: /adicionar membro/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/^nome$/i).fill('Rui Almeida')
    await dialog.getByRole('button', { name: /^guardar$/i }).click()
    await expectStep(7)

    await page.getByRole('button', { name: /adicionar membro/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/^nome$/i).fill('Carla Ferreira')
    await dialog.getByLabel('Programação', { exact: true }).check()
    await dialog.getByRole('button', { name: /^guardar$/i }).click()
    await expectStep(8)

    await page.getByRole('button', { name: /nova sala/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel(/nome da sala/i).fill('Laboratório 3')
    await dialog.getByLabel(/lotação/i).fill('24')
    await dialog.getByLabel(/tipo de sala/i).selectOption('lab')
    await dialog.getByRole('button', { name: /criar sala/i }).click()
    await expectStep(9)

    await page.getByRole('button', { name: /adicionar disciplina/i }).click()
    dialog = page.getByRole('dialog')
    await dialog.locator('select').selectOption({ index: 1 })
    await dialog.getByRole('button', { name: /^adicionar$/i }).click()
    await expectStep(10)

    await page.getByRole('button', { name: 'Impossível', exact: true }).click()
    await page.locator('button[data-timeslot-id]').last().click()
    await page.getByRole('button', { name: /guardar preferências/i }).click()
    await expectStep(11)

    await page.getByRole('button', { name: /gerar horário/i }).click()
    await expectStep(12)
    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(13)
    await page.locator('button[data-tutorial-target="approve-schedule"]').click()
    await expectStep(14)
    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(15)

    await page.locator('[data-tutorial-target="schedule-grid"] button:not([disabled])').first().click()
    await expectStep(16)
    dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: /criar ocorrência/i }).click()
    await dialog.getByRole('button', { name: /sim, criar ocorrência/i }).click()
    await expectStep(17)

    await page.getByRole('button', { name: /decidir/i }).click()
    await expectStep(18)
    dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: /substituída/i }).click()
    await expectStep(19)
    await dialog.locator('#substituteRecommendation').selectOption({ index: 1 })
    await dialog.getByLabel(/confirmo esta decisão operacional/i).check()
    await dialog.getByRole('button', { name: /confirmar decisão/i }).click()
    await expectStep(20)

    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(21)
    await page.getByRole('button', { name: /gerar novamente/i }).click()
    await page.getByRole('button', { name: /confirmar geração/i }).click()
    await expectStep(22)
    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(23)
    await page.getByTestId('tutorial-complete-step').click()
    await expectStep(24)
    await page.locator('button[data-tutorial-target="approve-schedule"]').click()
    await expect(page.getByTestId('tutorial-workspace')).toBeHidden()

    const savedState = await page.evaluate(() => {
      const entry = Object.entries(localStorage).find(([key]) => key.startsWith('cronos:tutorial:'))
      return entry ? JSON.parse(entry[1]) : null
    })
    expect(savedState.version).toBe(2)
    expect(savedState.status).toBe('COMPLETED')
    expect(savedState.stepId).toBe('repair_approve')
    expect(savedState.values.subject_create.completed).toBe(true)
    expect(savedState.values.module_add.completed).toBe(true)
    expect(savedState.values.course_create.completed).toBe(true)
    expect(savedState.values.class_create.completed).toBe(true)
    expect(savedState.values.teacher_add.completed).toBe(true)
    expect(savedState.values.teacher_competency.completed).toBe(true)
    expect(savedState.skippedStepIds).toEqual([])
    expect(savedState.simulationData).toBeUndefined()
    await expectNoAppCrash(page)
  })
})
