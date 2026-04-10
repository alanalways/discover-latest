import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

declare global {
  interface Window {
    __DL_BUILD__?: string
  }
}

const CHUNK_RELOAD_KEY = 'dl-chunk-reload-once'

function shouldHardReload(message: string) {
  return /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk|ChunkLoadError/i.test(message)
}

function reloadOnce() {
  if (sessionStorage.getItem(CHUNK_RELOAD_KEY) === window.__DL_BUILD__) return
  sessionStorage.setItem(CHUNK_RELOAD_KEY, window.__DL_BUILD__ || 'unknown-build')
  window.location.replace(window.location.pathname + window.location.search + window.location.hash)
}

window.addEventListener('error', (event) => {
  const target = event.target as HTMLScriptElement | null
  if (target?.tagName === 'SCRIPT' || shouldHardReload(event.message || '')) {
    reloadOnce()
  }
}, true)

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason instanceof Error ? event.reason.message : String(event.reason || '')
  if (shouldHardReload(reason)) {
    reloadOnce()
  }
})

const splash = document.getElementById('boot-splash')
const root = document.getElementById('root')

ReactDOM.createRoot(root!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

requestAnimationFrame(() => {
  splash?.remove()
})
