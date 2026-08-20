import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Tasks from '../views/Tasks.vue'
import Messages from '../views/Messages.vue'
import Calendar from '../views/Calendar.vue'
import Agent from '../views/Agent.vue'
import Connections from '../views/Connections.vue'
import Providers from '../views/Providers.vue'
import Settings from '../views/Settings.vue'

export default createRouter({ history: createWebHistory(), routes: [
  { path: '/', component: Home }, { path: '/tasks', component: Tasks }, { path: '/messages', component: Messages },
  { path: '/calendar', component: Calendar }, { path: '/agent', component: Agent }, { path: '/connections', component: Connections },
  { path: '/providers', component: Providers }, { path: '/settings', component: Settings }, { path: '/:pathMatch(.*)*', redirect: '/' }
] })
