import { http, HttpResponse } from 'msw'

export const handlers = [
  http.get('*/api/v1/school/calendar-events/', () => HttpResponse.json([])),
  http.get('*/api/v1/readiness/prevalidation', () => (
    HttpResponse.json({ status: 'READY', fingerprint: null, issues: [] })
  )),
]
