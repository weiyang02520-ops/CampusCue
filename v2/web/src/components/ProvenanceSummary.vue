<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  sourceName?: string | null
  sourceId?: number | null
  sourceMessageId?: string | null
  sourceTextReference?: string | null
  confidence?: number | null
  status?: string
  deadlineKnown?: boolean
}>()

const trustLabel = computed(() => {
  if (props.status === 'pending_confirm') return '需要确认'
  if (props.confidence == null) return '未提供置信度'
  return `已识别 · ${(props.confidence * 100).toFixed(0)}%`
})
const sourceLabel = computed(() => props.sourceName || (props.sourceId != null ? `消息源 #${props.sourceId}` : '未关联来源'))
const evidenceLabel = computed(() => props.sourceMessageId ? `消息引用 ${props.sourceMessageId}` : props.sourceTextReference ? '原文证据已保留' : '仅保留结构化结果')
</script>

<template>
  <div class="provenance-summary" aria-label="来源与识别依据">
    <span><b>来源</b>{{ sourceLabel }}</span>
    <span><b>可信度</b>{{ trustLabel }}</span>
    <span><b>证据</b>{{ evidenceLabel }}</span>
    <span v-if="deadlineKnown === false" class="provenance-warning">截止时间未识别</span>
  </div>
</template>
