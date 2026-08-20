import type { TaskCategory, TaskPriority, TaskStatus } from '../types/api'

export const TASK_CATEGORY_LABELS: Record<TaskCategory, string> = {
  homework: '作业',
  exam: '考试',
  activity: '活动',
  competition: '比赛',
  notice: '通知',
  other: '其他',
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: '进行中',
  pending_confirm: '待确认',
  done: '已完成',
  dismissed: '已忽略',
}

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: '低',
  normal: '普通',
  high: '高',
}

export const TASK_PRIORITY_OPTIONS = (Object.entries(TASK_PRIORITY_LABELS) as Array<[TaskPriority, string]>).map(([value, label]) => ({ value, label }))

export function taskCategoryLabel(value: TaskCategory) { return TASK_CATEGORY_LABELS[value] }
export function taskStatusLabel(value: TaskStatus) { return TASK_STATUS_LABELS[value] }
export function taskPriorityLabel(value: TaskPriority) { return TASK_PRIORITY_LABELS[value] }
