import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

function computeAppVersion() {
  const ts = new Date().toISOString()
  try {
    const sha = execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim()
    return `${sha}-${ts}`
  } catch {
    return `dev-${ts}`
  }
}

const APP_VERSION = computeAppVersion()

function writeVersionFile() {
  return {
    name: 'write-version-file',
    closeBundle() {
      try {
        const outDir = path.resolve(__dirname, 'dist')
        fs.mkdirSync(outDir, { recursive: true })
        fs.writeFileSync(path.join(outDir, 'version.txt'), APP_VERSION, 'utf8')
      } catch {
        // non-fatal
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), writeVersionFile()],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router', 'react-router-dom'],
          antd: ['antd', '@ant-design/icons'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
