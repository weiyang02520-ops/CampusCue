import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Source, Provider, Message, Reminder, Settings } from '../types/api'
export const useResourcesStore = defineStore('resources', () => {
  const sources = ref<Source[]>([]); const providers = ref<Provider[]>([]); const messages = ref<Message[]>([]); const reminders = ref<Reminder[]>([]); const settings = ref<Settings>({ settings: { timezone:'Asia/Shanghai', theme:'system', message_retention_days:30, reminder_default_enabled:true, reminder_min_lead_seconds:60, reminder_quiet_start_hour:23, reminder_quiet_end_hour:8 }, restart_required: [] }); const loading = ref(false)
  async function loadAll() { loading.value = true; await Promise.allSettled([loadSources(), loadProviders(), loadMessages(), loadReminders(), loadSettings()]); loading.value = false }
  async function loadSources() { sources.value = (await api.sources()).items }
  async function loadProviders() { providers.value = (await api.providers()).items }
  async function loadMessages(query = 'limit=20') { messages.value = (await api.messages(query)).items }
  async function loadReminders() { reminders.value = (await api.reminders('limit=50')).items }
  async function loadSettings() { settings.value = await api.settings() }
  return { sources, providers, messages, reminders, settings, loading, loadAll, loadSources, loadProviders, loadMessages, loadReminders, loadSettings }
})
