<script setup>
/**
 * Which group's board am I looking at.
 *
 * A native `<select>`, deliberately. A custom dropdown would need keyboard
 * handling, focus trapping and a portal to escape the header's stacking context,
 * and it would look the same. The one thing worth adding is the open-task count
 * per group, which turns the picker into a summary as well as a control.
 *
 * Hidden entirely when there is only one group. On a single-student install that
 * is the normal case, and a dropdown with one option is noise in the header of a
 * board whose whole design brief was "clean at first glance".
 */
import { computed } from 'vue'

const props = defineProps({
  sources: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

const visible = computed(() => props.sources.length > 1)

const current = computed(
  () => props.sources.find((s) => s.umo === props.modelValue) ?? null,
)
</script>

<template>
  <label v-if="visible" class="picker">
    <span class="lbl">来源</span>
    <select
      class="select"
      :value="modelValue"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option v-for="s in sources" :key="s.umo" :value="s.umo">
        {{ s.label }}{{ s.open_tasks ? ` （${s.open_tasks}）` : '' }}
      </option>
    </select>
  </label>
  <!-- With one source the label still carries information: which group is being
       watched. Rendered as plain text rather than a disabled control. -->
  <p v-else-if="current" class="single">{{ current.label }}</p>
</template>

<style scoped>
.picker {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--text-xs);
  color: var(--ink-faint);
}

.select {
  font: inherit;
  font-size: var(--text-sm);
  padding: var(--sp-1) var(--sp-2);
  color: var(--ink);
  background: var(--paper-raised);
  border: 1px solid var(--rule-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
  max-width: 240px;
}
.select:focus { outline: none; border-color: var(--accent); }

.single {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--ink-faint);
}
</style>
