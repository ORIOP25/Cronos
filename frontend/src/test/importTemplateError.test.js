// @vitest-environment jsdom
import axios from 'axios'
import { describe, expect, it, vi } from 'vitest'
import { createApiClient } from '../apiClient'
import { downloadBulkImportTemplate } from '../features/imports/data'
import { getApiErrorMessage, getApiErrorPresentation } from '../utils/apiErrors'

function arrayBufferOf(value) {
  return new TextEncoder().encode(value).buffer
}

function isArrayBuffer(value) {
  return Object.prototype.toString.call(value) === '[object ArrayBuffer]'
}

function badRequestAdapter(data) {
  return vi.fn(async (config) => {
    throw new axios.AxiosError(
      'Request failed with status code 400',
      'ERR_BAD_REQUEST',
      config,
      {},
      { config, data, headers: {}, status: 400, statusText: 'Bad Request' },
    )
  })
}

async function downloadError(data) {
  const client = createApiClient({ adapter: badRequestAdapter(data), authenticate: false })
  try {
    await downloadBulkImportTemplate(client, 'class_availability')
  } catch (error) {
    return error
  }
  throw new Error('expected the download to fail')
}

describe('class availability template transport errors', () => {
  it('decodes a JSON error returned as an arraybuffer into the exact no-grid message', async () => {
    const error = await downloadError(
      arrayBufferOf(
        JSON.stringify({
          detail: {
            code: 'bad_request',
            context: { reason: 'no_grid_blocks' },
            reference: 'REQ123ABC',
          },
        }),
      ),
    )

    expect(error.response.status).toBe(400)
    expect(error.response.data.detail.code).toBe('bad_request')
    expect(getApiErrorPresentation(error).reference).toBe('REQ123ABC')
    expect(getApiErrorMessage(error, 'fallback')).toBe('A escola ainda não configurou blocos.')
  })

  it('leaves a non-JSON arraybuffer untouched and never shows raw text', async () => {
    const error = await downloadError(arrayBufferOf('Internal Server Error: secret'))

    expect(isArrayBuffer(error.response.data)).toBe(true)
    const message = getApiErrorMessage(error, 'fallback')
    expect(message).toBe('Não foi possível concluir o pedido. Tente novamente.')
    expect(message).not.toContain('secret')
  })

  it('ignores a JSON arraybuffer that is not a structured error', async () => {
    const error = await downloadError(arrayBufferOf(JSON.stringify('plain text')))

    expect(isArrayBuffer(error.response.data)).toBe(true)
    expect(getApiErrorMessage(error, 'fallback')).toBe(
      'Não foi possível concluir o pedido. Tente novamente.',
    )
  })
})
