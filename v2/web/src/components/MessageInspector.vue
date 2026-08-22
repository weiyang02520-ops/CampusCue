<script setup lang="ts">
import { computed } from 'vue'
import { X, MessageSquareText } from 'lucide-vue-next'
import type { MessageDetail } from '../types/api'
const props = defineProps<{ message: MessageDetail; sourceName?: string | null }>()
const result = computed(() => props.message.normalized_result || {})
const audit = computed(() => props.message.audit || {})
const extractionReason = computed(() => String((audit.value.l3 as Record<string, unknown> | undefined)?.reason || props.message.reason || props.message.error || '无额外说明'))
const trustLabel = computed(() => props.message.status === 'pending_confirm' ? '需要确认' : props.message.confidence == null ? '未提供' : `已识别 · ${(props.message.confidence * 100).toFixed(0)}%`)
</script>

<template>
  <div class="detail-list">
    <div><span>状态</span><strong>{{ message.status }}</strong></div>
    <div><span>识别可信度</span><strong>{{ trustLabel }}</strong></div>
    <div><span>关联任务</span><strong>{{ message.task_id ? `任务 #${message.task_id}` : '未创建任务' }}</strong></div>
    <div><span>识别结果</span><strong>{{ result.title ? `${result.title}${result.course ? ` · ${result.course}` : ''}` : '没有识别出任务' }}</strong></div>
    <div><span>处理原因</span><strong>{{ extractionReason }}</strong></div>
    <details class="detail-advanced"><summary>来源与证据</summary><div><span>来源</span><strong>{{ props.sourceName || (message.source_id == null ? '未知' : `消息源 #${message.source_id}`) }}</strong></div><div><span>消息引用</span><strong>{{ message.source_message_id }}</strong></div><div><span>截止时间</span><strong>{{ result.deadline_phrase || '未识别，待补充' }}</strong></div><div><span>消息保留</span><strong>{{ message.text_retained ? '按策略保存' : '未保留原文' }}</strong></div></details>
    <div class="retention-note"><span><X v-if="!message.text_retained" :size="15" /><MessageSquareText v-else :size="15" />{{ message.text_retained ? '原文按保留策略保存' : '原文未保留，符合隐私设置' }}</span></div>
  </div>
</template>
