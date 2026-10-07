import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveBuildRevision } from './write-build-revision.mjs'

test('Cloudflare builds require the provider full revision', () => {
  const revision = 'a'.repeat(40)
  assert.deepEqual(resolveBuildRevision({ CF_PAGES: '1', CF_PAGES_COMMIT_SHA: revision }), { schema_version: 1, revision, verifiable: true, source: 'cloudflare-pages' })
  for (const CF_PAGES_COMMIT_SHA of [undefined, '', 'abc123', 'x'.repeat(40)]) {
    assert.throws(() => resolveBuildRevision({ CF_PAGES: '1', CF_PAGES_COMMIT_SHA }), /revision/)
  }
})

test('local builds cannot claim a production revision from arbitrary environment', () => {
  assert.deepEqual(resolveBuildRevision({ GITHUB_SHA: 'a'.repeat(40), DEPLOYED_REVISION: 'b'.repeat(40) }), { schema_version: 1, revision: null, verifiable: false, source: 'local' })
})
