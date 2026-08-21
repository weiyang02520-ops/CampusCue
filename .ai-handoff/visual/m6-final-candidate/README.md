# CampusCue M6 Final Candidate Evidence

Generated from one deterministic M5-backed demo dataset after the legacy Appearance selector cleanup. All comparison captures use the same routes and data; only the frontend visual style changes.

| File | Viewport | Theme | Route / state | Purpose |
|---|---:|---|---|---|
| `compare/home-glass-1440.png` | 1440 | Glass | Home / default | Glass identity |
| `compare/home-dark-1440.png` | 1440 | Dark | Home / default | Dark identity |
| `compare/home-neumorphism-1440.png` | 1440 | Neu | Home / default | Neu identity |
| `compare/tasks-glass-1440.png` | 1440 | Glass | Tasks / default | Task hierarchy |
| `compare/tasks-dark-1440.png` | 1440 | Dark | Tasks / default | Solid dark surfaces |
| `compare/tasks-neumorphism-1440.png` | 1440 | Neu | Tasks / default | Flat rows, tactile controls |
| `compare/calendar-glass-1440.png` | 1440 | Glass | Calendar / default | Calendar scanability |
| `compare/calendar-dark-1440.png` | 1440 | Dark | Calendar / default | Dark calendar hierarchy |
| `compare/calendar-neumorphism-1440.png` | 1440 | Neu | Calendar / default | Flat cells, selected-state material |
| `compare/messages-glass-1440.png` | 1440 | Glass | Messages / default | List and inspector readability |
| `compare/messages-dark-1440.png` | 1440 | Dark | Messages / default | Low-glare message workspace |
| `compare/messages-neumorphism-1440.png` | 1440 | Neu | Messages / default | Flat message rows |
| `compare/agent-glass-1440.png` | 1440 | Glass | Agent / default | Glass canvas and composer |
| `compare/agent-dark-1440.png` | 1440 | Dark | Agent / default | Solid agent workspace |
| `compare/agent-neumorphism-1440.png` | 1440 | Neu | Agent / default | Tactile context and composer |
| `compare/connections-glass-1440.png` | 1440 | Glass | Connections / default | Connection cards |
| `compare/connections-dark-1440.png` | 1440 | Dark | Connections / default | Dark card hierarchy |
| `compare/connections-neumorphism-1440.png` | 1440 | Neu | Connections / default | Raised card surfaces |
| `compare/providers-glass-1440.png` | 1440 | Glass | Providers / default | Provider summary |
| `compare/providers-dark-1440.png` | 1440 | Dark | Providers / default | Dark provider summary |
| `compare/providers-neumorphism-1440.png` | 1440 | Neu | Providers / default | Neu provider summary |
| `compare/settings-glass-1440.png` | 1440 | Glass | Settings / four-style selector | Single selector |
| `compare/settings-dark-1440.png` | 1440 | Dark | Settings / four-style selector | Single selector |
| `compare/settings-neumorphism-1440.png` | 1440 | Neu | Settings / four-style selector | Single selector |
| `mobile/home-glass-390.png` | 390 | Glass | Home / mobile | Mobile layout |
| `mobile/home-dark-390.png` | 390 | Dark | Home / mobile | Mobile layout |
| `mobile/home-neumorphism-390.png` | 390 | Neu | Home / mobile | Mobile layout |
| `mobile/agent-glass-390.png` | 390 | Glass | Agent / mobile | Composer clearance |
| `mobile/agent-dark-390.png` | 390 | Dark | Agent / mobile | Composer clearance |
| `mobile/agent-neumorphism-390.png` | 390 | Neu | Agent / mobile | Composer clearance |
| `mobile/settings-theme-selector-390.png` | 390 | Glass | Settings / four-style selector | No overflow, single selector |
| `mobile/settings-dark-390.png` | 390 | Dark | Settings / four-style selector | No overflow |
| `mobile/settings-neumorphism-390.png` | 390 | Neu | Settings / four-style selector | No overflow |
| `theme/theme-selector-1440.png` | 1440 | System | Settings / selector | System option and four choices |
| `theme/theme-selector-390.png` | 390 | System | Settings / selector | Mobile selector |
| `theme/system-light-1440.png` | 1440 | System → Glass | Settings / OS light | Resolved DOM state |
| `theme/system-dark-1440.png` | 1440 | System → Dark | Settings / OS dark | Resolved DOM state |

Automated coverage in `v2/web/tests/e2e/m6-final-candidate.spec.ts` checks 1440/1024/768/390 overflow, System OS resolution, explicit-style OS independence, persistence, Axe on Home/Settings/Agent/More sheet/Task dialog, and the final screenshot set.
