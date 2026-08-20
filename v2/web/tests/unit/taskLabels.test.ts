import { describe, expect, it } from 'vitest'
import { TASK_PRIORITY_OPTIONS, taskCategoryLabel, taskStatusLabel } from '../../src/utils/taskLabels'

describe('task labels', () => {
  it('keeps the canonical priority vocabulary', () => {
    expect(TASK_PRIORITY_OPTIONS).toEqual([{ value: 'low', label: '低' }, { value: 'normal', label: '普通' }, { value: 'high', label: '高' }])
  })
  it('localizes category and status enums', () => {
    expect(taskCategoryLabel('homework')).toBe('作业')
    expect(taskCategoryLabel('competition')).toBe('比赛')
    expect(taskStatusLabel('pending_confirm')).toBe('待确认')
  })
})
