import { describe, expect, it, vi } from 'vitest'
import {
  createBulkImportReport,
  fileToBase64,
  filesToPayload,
} from '../features/imports/data'

function csvFile(content, name = 'salas.csv') {
  return new File([content], name, { type: 'text/csv' })
}

describe('bulk import file utilities', () => {
  it('preserves UTF-8 BOM and converts a file to base64', async () => {
    const file = csvFile('\ufeffname;type;capacity\r\nSala;normal;20\r\n')

    await expect(fileToBase64(file)).resolves.toBe(
      '77u/bmFtZTt0eXBlO2NhcGFjaXR5DQpTYWxhO25vcm1hbDsyMA0K',
    )
  })

  it('rejects files without a UTF-8 BOM before upload', async () => {
    await expect(fileToBase64(csvFile('name;type;capacity\r\n'))).rejects.toMatchObject({
      code: 'utf8_bom_required',
    })
  })

  it('builds the backend payload without changing selected files', async () => {
    const rooms = csvFile('\ufeffname;type;capacity\r\nSala;normal;20\r\n')
    const subjects = csvFile('\ufeffname;required_room_type;module_name;module_code;module_hours;module_order\r\nDisciplina;normal;;;;\r\n', 'disciplinas.csv')

    await expect(filesToPayload({ rooms, subjects })).resolves.toEqual({
      rooms: { filename: 'salas.csv', content_base64: expect.any(String) },
      subjects: { filename: 'disciplinas.csv', content_base64: expect.any(String) },
    })
  })

  it('creates an Excel-safe semicolon issue report with a BOM', () => {
    const report = createBulkImportReport([
      { severity: 'error', resource: 'rooms', line: 2, field: 'name', code: 'x', message: '=unsafe' },
    ])

    expect(report).toBeInstanceOf(Blob)
    expect(report.type).toBe('text/csv;charset=utf-8')
  })

  it('revokes object URLs after downloading a report', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const click = vi.fn()
    vi.spyOn(document, 'createElement').mockReturnValue({
      href: '', download: '', click,
    })

    const report = createBulkImportReport([])
    const { downloadBlob } = await import('../features/imports/data')
    downloadBlob(report, 'issues.csv')

    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
  })
})
