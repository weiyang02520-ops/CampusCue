import assert from 'node:assert/strict'
import test from 'node:test'

import {
  apiErrorMessage,
  connectionLabel,
  groupTasks,
  mergeTask,
  restoreTask,
  streamOpened,
} from '../src/boardState.js'

const task = (id, fields = {}) => ({
  task_id: id,
  title: `任务${id}`,
  umo: 'qq:GroupMessage:1',
  status: 'active',
  deadline: null,
  ...fields,
})

test('the first stream open does not resync but a reconnect does', () => {
  const first = streamOpened(false)
  const second = streamOpened(first.hasOpened)

  assert.equal(first.shouldResync, false)
  assert.equal(second.shouldResync, true)
})

test('network failures are translated into actions a student can take', () => {
  assert.match(apiErrorMessage({ status: 401, detail: 'Unauthorized' }), /重新登录/)
  assert.match(apiErrorMessage({ aborted: true }), /请求超时/)
  assert.match(apiErrorMessage({ online: false }), /网络不可用/)
  assert.equal(
    apiErrorMessage({ status: 422, statusText: 'Error', detail: '标题不能为空' }),
    '标题不能为空',
  )
})

test('connection status distinguishes startup, retrying and prolonged offline', () => {
  const now = Date.parse('2026-08-03T06:00:00Z')
  assert.equal(connectionLabel(true, null, now), '实时监听中')
  assert.equal(connectionLabel(false, null, now), '正在连接')
  assert.equal(connectionLabel(false, now - 30_000, now), '正在重连')
  assert.equal(connectionLabel(false, now - 125_000, now), '已离线 2 分钟')
})

test('partial reminder payloads and another group never replace cards', () => {
  const current = [task('a')]

  assert.equal(mergeTask(current, { task_id: 'a', delivered: true }).tasks, current)
  assert.equal(
    mergeTask(current, task('b', { umo: 'qq:GroupMessage:2' }), 'qq:GroupMessage:1')
      .tasks,
    current,
  )
})

test('a failed optimistic removal restores only the affected card', () => {
  const previous = [task('a'), task('b')]
  const duringRequest = [task('new'), task('b', { title: '并发更新' })]

  const restored = restoreTask(duringRequest, previous, 'a')

  assert.deepEqual(restored.map((item) => item.task_id), ['a', 'new', 'b'])
  assert.equal(restored.find((item) => item.task_id === 'b').title, '并发更新')
})

test('today follows the Asia Shanghai calendar boundary', () => {
  const now = Date.parse('2026-08-03T15:30:00Z') // 23:30 in Shanghai
  const grouped = groupTasks(
    [
      task('today', { deadline: '2026-08-03T15:45:00Z' }),
      task('tomorrow', { deadline: '2026-08-03T16:15:00Z' }),
    ],
    now,
  )
  const byKey = Object.fromEntries(grouped.map((bucket) => [bucket.key, bucket.items]))

  assert.deepEqual(byKey.today.map((item) => item.task_id), ['today'])
  assert.deepEqual(byKey.soon.map((item) => item.task_id), ['tomorrow'])
})
