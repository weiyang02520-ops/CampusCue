const HOUR = 3600_000
const DAY = 24 * HOUR
const CAMPUS_OFFSET_MS = 8 * HOUR

export function streamOpened(hasOpened) {
  return { hasOpened: true, shouldResync: hasOpened }
}

export function apiErrorMessage({
  status = 0,
  statusText = '',
  detail = '',
  aborted = false,
  online = true,
} = {}) {
  if (status === 401 || status === 403) {
    return '登录已失效，请先在 AstrBot 管理面板重新登录，再刷新本页'
  }
  if (aborted) return '请求超时，服务可能仍在启动或暂时无响应，请稍后重试'
  if (!status && !online) return '当前网络不可用；恢复连接后看板会自动同步'
  if (!status) return '无法连接课讯服务，请确认程序仍在运行'
  return detail || `${status} ${statusText}`.trim()
}

export function connectionLabel(connected, disconnectedAt, nowMs) {
  if (connected) return '实时监听中'
  if (!disconnectedAt) return '正在连接'
  const elapsed = Math.max(0, nowMs - disconnectedAt)
  if (elapsed < 60_000) return '正在重连'
  return `已离线 ${Math.max(1, Math.floor(elapsed / 60_000))} 分钟`
}

export function mergeTask(tasks, task, umo = '') {
  if (!task?.task_id || !task?.title || !task?.umo) {
    return { tasks, inserted: false }
  }
  if (umo && task.umo !== umo) return { tasks, inserted: false }

  const index = tasks.findIndex((item) => item.task_id === task.task_id)
  if (index === -1) {
    return { tasks: [task, ...tasks], inserted: true }
  }
  const next = [...tasks]
  next[index] = task
  return { tasks: next, inserted: false }
}

export function restoreTask(tasks, previous, taskId) {
  const originalIndex = previous.findIndex((task) => task.task_id === taskId)
  if (originalIndex === -1) return tasks

  const original = previous[originalIndex]
  const currentIndex = tasks.findIndex((task) => task.task_id === taskId)
  if (currentIndex !== -1) {
    const next = [...tasks]
    next[currentIndex] = original
    return next
  }

  const next = [...tasks]
  next.splice(Math.min(originalIndex, next.length), 0, original)
  return next
}

export function groupTasks(tasks, nowMs) {
  const campusNow = new Date(nowMs + CAMPUS_OFFSET_MS)
  const startOfTodayUtc =
    Date.UTC(
      campusNow.getUTCFullYear(),
      campusNow.getUTCMonth(),
      campusNow.getUTCDate(),
    ) - CAMPUS_OFFSET_MS
  const endOfTodayUtc = startOfTodayUtc + DAY - 1
  const buckets = [
    { key: 'overdue', label: '已逾期', items: [] },
    { key: 'today', label: '今天', items: [] },
    { key: 'soon', label: '三天内', items: [] },
    { key: 'later', label: '之后', items: [] },
    { key: 'undated', label: '待定时间', items: [] },
    { key: 'done', label: '已完成 / 已忽略', items: [] },
  ]
  const by = Object.fromEntries(buckets.map((bucket) => [bucket.key, bucket]))

  for (const task of tasks) {
    if (task.status === 'pending_confirm') continue
    if (task.status === 'done' || task.status === 'dismissed') {
      by.done.items.push(task)
      continue
    }
    if (!task.deadline) {
      by.undated.items.push(task)
      continue
    }
    const at = new Date(task.deadline).getTime()
    if (at < nowMs) by.overdue.items.push(task)
    else if (at <= endOfTodayUtc) by.today.items.push(task)
    else if (at < nowMs + 3 * DAY) by.soon.items.push(task)
    else by.later.items.push(task)
  }

  for (const bucket of buckets) {
    bucket.items.sort((left, right) => {
      if (!left.deadline) return 1
      if (!right.deadline) return -1
      return new Date(left.deadline) - new Date(right.deadline)
    })
  }
  return buckets.filter((bucket) => bucket.items.length)
}
