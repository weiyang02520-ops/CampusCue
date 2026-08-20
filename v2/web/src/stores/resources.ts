import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Source, Provider, Message, Reminder, Settings } from '../types/api'
export const useResourcesStore = defineStore('resources', () => {
  const sources = ref<Source[]>([]); const providers = ref<Provider[]>([]); const messages = ref<Message[]>([]); const reminders = ref<Reminder[]>([]); const settings = ref<Settings>({ settings: {}, restart_required: [] }); const loading = ref(false)
  async function loadAll() { loading.value = true; await Promise.allSettled([loadSources(), loadProviders(), loadMessages(), loadReminders(), loadSettings()]); loading.value = false }
  async function loadSources() { sources.value = (await api.sources()).items }
  async function loadProviders() { providers.value = (await api.providers()).items }
  async function loadMessages() { messages.value = (await api.messages('limit=20')).items }
  async function loadReminders() { reminders.value = (await api.reminders('limit=50')).items }
  async function loadSettings() { settings.value = await api.settings() }
  return { sources, providers, messages, reminders, settings, loading, loadAll, loadSources, loadProviders, loadMessages, loadReminders, loadSettings }
})
