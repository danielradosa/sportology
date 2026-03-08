import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { Layout, Skeleton, Modal, Typography } from 'antd'
import AppHeader from './components/Layout/AppHeader'
import { AuthProvider } from './hooks/useAuth'
import { APP_VERSION } from './version'

const Home = lazy(() => import('./pages/Home'))
const Login = lazy(() => import('./pages/Login'))
const Signup = lazy(() => import('./pages/Signup'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Analyzer = lazy(() => import('./pages/Analyzer'))
const Bot = lazy(() => import('./pages/Bot'))
const AdminPanel = lazy(() => import('./pages/AdminPanel'))

const { Content, Footer } = Layout
const { Text } = Typography

function RouteFallback() {
  return (
    <div className='route-fallback'>
      <Skeleton active paragraph={{ rows: 7 }} />
    </div>
  )
}

function App() {
  const [updateOpen, setUpdateOpen] = useState(false)
  const [serverVersion, setServerVersion] = useState<string>('')
  const wsRef = useRef<WebSocket | null>(null)

  const shouldPrompt = useMemo(() => {
    return !!serverVersion && serverVersion !== APP_VERSION
  }, [serverVersion])

  useEffect(() => {
    // Connect to backend update stream.
    // Backend sends current deployed frontend version and broadcasts when it changes.
    try {
      const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/updates`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'version' && typeof msg?.version === 'string') {
            setServerVersion(msg.version)
          }
          if (msg?.type === 'deploy' && typeof msg?.version === 'string') {
            setServerVersion(msg.version)
          }
        } catch {
          // ignore
        }
      }

      ws.onclose = () => {
        wsRef.current = null
      }

      return () => {
        try {
          ws.close()
        } catch {
          // ignore
        }
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    if (shouldPrompt) setUpdateOpen(true)
  }, [shouldPrompt])

  return (
    <AuthProvider>
      <Router>
        <Layout className='app-shell'>
          <AppHeader />
          <Content className='app-content'>
            <div className='page-container'>
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  <Route path='/' element={<Home />} />
                  <Route path='/login' element={<Login />} />
                  <Route path='/signup' element={<Signup />} />
                  <Route path='/dashboard' element={<Dashboard />} />
                  <Route path='/analyzer' element={<Analyzer />} />
                  <Route path='/bot' element={<Bot />} />
                  <Route path='/admin-ui' element={<AdminPanel />} />
                </Routes>
              </Suspense>
            </div>
          </Content>
          <Footer className='app-footer'>
            © {new Date().getFullYear()} · SAPI | SPORTOLOGY + API by{' '}
            <a href='https://danielradosa.com' target='_blank' rel='noreferrer'>
              Daniel Radosa
            </a>
          </Footer>

          <Modal
            title='Update available'
            open={updateOpen}
            okText='Refresh'
            cancelText='Later'
            onOk={() => window.location.reload()}
            onCancel={() => setUpdateOpen(false)}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Text>A new version of the site was deployed.</Text>
              <Text type='secondary'>
                Current: {APP_VERSION || 'unknown'}
                <br />
                New: {serverVersion || 'unknown'}
              </Text>
            </div>
          </Modal>
        </Layout>
      </Router>
    </AuthProvider>
  )
}

export default App
