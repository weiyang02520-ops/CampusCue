<script setup lang="ts">
defineProps({ eyebrow: String, title: { type: String, required: true }, description: String })
</script>
<template><div class="page-header"><div><p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p><h2>{{ title }}</h2><p v-if="description" class="page-description">{{ description }}</p></div><div class="page-actions"><slot /></div></div></template>
