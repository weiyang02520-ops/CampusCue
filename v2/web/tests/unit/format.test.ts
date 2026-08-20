import { describe, expect, it } from 'vitest'
import { formatDate, formatTime, relative } from '../../src/composables/useFormat'

describe('date presentation', () => {
  it('uses an explicit timezone instead of string slicing', () => {
    expect(formatDate('2026-08-20T00:30:00Z', 'Asia/Shanghai')).toContain('20')
    expect(formatTime('2026-08-20T00:30:00Z', 'Asia/Shanghai')).toContain('08')
  })
  it('describes relative deadlines', () => { expect(relative(new Date(Date.now() + 86_400_000).toISOString())).toBe('明天') })
})
