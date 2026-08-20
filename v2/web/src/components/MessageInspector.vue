<script setup lang="ts">
import { X, MessageSquareText } from 'lucide-vue-next'
import type { MessageDetail } from '../types/api'
defineProps<{ message: MessageDetail }>()
</script>

<template>
  <div class="detail-list">
    <div><span>状态</span><strong>{{ message.status }}</strong></div>
    <div><span>识别置信度</span><strong>{{ message.confidence == null ? '未提供' : `${(message.confidence * 100).toFixed(0)}%` }}</strong></div>
    <div><span>关联任务</span><strong>{{ message.task_id ? `任务 #${message.task_id}` : '未创建任务' }}</strong></div>
    <div><span>处理原因</span><strong>{{ message.reason || message.error || '无额外说明' }}</strong></div>
    <details class="detail-advanced"><summary>更多信息</summary><div><span>来源</span><strong>#{{ message.source_id ?? '未知' }}</strong></div><div><span>消息保留</span><strong>{{ message.text_retained ? '按策略保存' : '未保留原文' }}</strong></div></details>
    <div class="retention-note"><span><X v-if="!message.text_retained" :size="15" /><MessageSquareText v-else :size="15" />{{ message.text_retained ? '原文按保留策略保存' : '原文未保留，符合隐私设置' }}</span></div>
  </div>
</template>
