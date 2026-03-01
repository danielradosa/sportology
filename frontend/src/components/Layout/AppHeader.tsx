import { Layout, Menu, Button, Space, Typography, Grid, Drawer } from 'antd'
import { useEffect } from 'react'
import {
  UserOutlined,
  DashboardOutlined,
  HomeOutlined,
  LoginOutlined,
  LogoutOutlined,
  DotChartOutlined,
  RobotOutlined,
  MenuOutlined,
} from '@ant-design/icons'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth, useAuthStore } from '../../hooks/useAuth'
import { useState } from 'react'

const { Header } = Layout
const { Text } = Typography
const { useBreakpoint } = Grid

function AppHeader() {
  const { isAuthenticated, user, logout } = useAuth()
  const accessToken = useAuthStore((s) => s.accessToken)
  const location = useLocation()
  const navigate = useNavigate()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [open, setOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const [adminEmail, setAdminEmail] = useState<string | null>(null)

  useEffect(() => {
    const loadAdminEmail = async () => {
      if (!isAuthenticated || !accessToken) return
      try {
        const res = await fetch('/api/v1/admin-email', {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        if (!res.ok) return
        const json = await res.json()
        setAdminEmail((json.admin_email || '').toLowerCase())
      } catch {
        // ignore
      }
    }
    loadAdminEmail()
  }, [isAuthenticated, accessToken])

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: <Link to='/'>Home</Link> },
    ...(isAuthenticated
      ? [
          {
            key: '/dashboard',
            icon: <DashboardOutlined />,
            label: <Link to='/dashboard'>Dashboard</Link>,
          },
          {
            key: '/analyzer',
            icon: <DotChartOutlined />,
            label: <Link to='/analyzer'>Analyzer</Link>,
          },
          { key: '/bot', icon: <RobotOutlined />, label: <Link to='/bot'>Bot</Link> },
          ...(adminEmail && user?.email?.toLowerCase() === adminEmail
            ? [
                { key: '/admin-ui', icon: <UserOutlined />, label: <Link to='/admin-ui'>Admin</Link> },
              ]
            : []),
        ]
      : []),
  ]

  return (
    <Header className='app-header'>
      <div className='brand-wrap'>
        <Link to='/' className='brand-link'>
          🔮 SAPI | SPORTOLOGY + API
        </Link>
      </div>

      {!isMobile && (
        <>
          <Menu mode='horizontal' selectedKeys={[location.pathname]} items={menuItems} className='top-menu' />
          <Space>
            {isAuthenticated ? (
              <>
                <Text className='header-user'>
                  <UserOutlined /> {user?.email}
                </Text>
                <Button danger icon={<LogoutOutlined />} onClick={handleLogout}>
                  Logout
                </Button>
              </>
            ) : (
              <>
                <Link to='/login'>
                  <Button type='primary' icon={<LoginOutlined />}>
                    Login
                  </Button>
                </Link>
                <Link to='/signup'>
                  <Button>Sign Up</Button>
                </Link>
              </>
            )}
          </Space>
        </>
      )}

      {isMobile && (
        <Button type='text' icon={<MenuOutlined />} onClick={() => setOpen(true)} />
      )}

      <Drawer placement='right' open={open} onClose={() => setOpen(false)} title='Menu'>
        <Menu
          mode='inline'
          selectedKeys={[location.pathname]}
          items={menuItems}
          style={{ borderInlineEnd: 0, marginBottom: 12 }}
          onClick={() => setOpen(false)}
        />

        {isAuthenticated ? (
          <Space direction='vertical' style={{ width: '100%' }}>
            <Text type='secondary'>{user?.email}</Text>
            <Button danger icon={<LogoutOutlined />} onClick={handleLogout} block>
              Logout
            </Button>
          </Space>
        ) : (
          <Space direction='vertical' style={{ width: '100%' }}>
            <Link to='/login' onClick={() => setOpen(false)}>
              <Button type='primary' icon={<LoginOutlined />} block>
                Login
              </Button>
            </Link>
            <Link to='/signup' onClick={() => setOpen(false)}>
              <Button block>Sign Up</Button>
            </Link>
          </Space>
        )}
      </Drawer>
    </Header>
  )
}

export default AppHeader
