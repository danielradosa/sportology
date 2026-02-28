import { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { Layout, Skeleton } from 'antd'
import AppHeader from './components/Layout/AppHeader'
import { AuthProvider } from './hooks/useAuth'

const Home = lazy(() => import('./pages/Home'))
const Login = lazy(() => import('./pages/Login'))
const Signup = lazy(() => import('./pages/Signup'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Analyzer = lazy(() => import('./pages/Analyzer'))
const Bot = lazy(() => import('./pages/Bot'))
const AdminPlayers = lazy(() => import('./pages/AdminPlayers'))

const { Content, Footer } = Layout

function RouteFallback() {
  return (
    <div className='route-fallback'>
      <Skeleton active paragraph={{ rows: 7 }} />
    </div>
  )
}

function App() {
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
                  <Route path='/admin/players' element={<AdminPlayers />} />
                </Routes>
              </Suspense>
            </div>
          </Content>
          <Footer className='app-footer'>
            © {new Date().getFullYear()} · SPORTOLOGY + API by{' '}
            <a href='https://danielradosa.com' target='_blank' rel='noreferrer'>
              Daniel Radosa
            </a>
          </Footer>
        </Layout>
      </Router>
    </AuthProvider>
  )
}

export default App
