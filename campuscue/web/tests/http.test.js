import assert from 'node:assert/strict'
import test from 'node:test'

import { requestJson } from '../src/http.js'

function response(status, body, statusText = '') {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    async json() {
      return body
    },
  }
}

test('requestJson unwraps validation details and authentication failures', async () => {
  await assert.rejects(
    requestJson('/bad', {}, { fetchImpl: async () => response(422, { detail: '标题不能为空' }) }),
    /标题不能为空/,
  )
  await assert.rejects(
    requestJson('/auth', {}, { fetchImpl: async () => response(401, { detail: 'no' }) }),
    /重新登录/,
  )
})

test('requestJson aborts a stalled request with a useful timeout', async () => {
  const stalled = (_url, options) =>
    new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        reject(new DOMException('aborted', 'AbortError'))
      })
    })

  await assert.rejects(
    requestJson('/slow', {}, { fetchImpl: stalled, timeoutMs: 5 }),
    /请求超时/,
  )
})

test('requestJson rejects malformed successful responses', async () => {
  const malformed = async () => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    async json() {
      throw new SyntaxError('bad json')
    },
  })

  await assert.rejects(
    requestJson('/broken', {}, { fetchImpl: malformed }),
    /无法读取的数据/,
  )
})
