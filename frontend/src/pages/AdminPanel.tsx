import { useEffect, useState } from 'react'
import { Card, Segmented, Modal, Input, Button, Space } from 'antd'
import AdminPlayers from './AdminPlayers'
import AdminUsers from './AdminUsers'

const AdminPanel = () => {
  const [view, setView] = useState<'players' | 'users'>('players')
  const [adminKey, setAdminKey] = useState('')
  const [showKeyModal, setShowKeyModal] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('admin_key') || ''
    if (!stored) {
      setShowKeyModal(true)
    } else {
      setAdminKey(stored)
    }
  }, [])

  const saveKey = () => {
    if (!adminKey) return
    localStorage.setItem('admin_key', adminKey)
    setShowKeyModal(false)
  }

  return (
    <Card title='Admin'>
      <Segmented
        value={view}
        onChange={(val) => setView(val as 'players' | 'users')}
        options={[
          { label: 'Players', value: 'players' },
          { label: 'Users', value: 'users' },
        ]}
        style={{ marginBottom: 16 }}
      />
      {view === 'players' ? <AdminPlayers adminKey={adminKey} /> : <AdminUsers adminKey={adminKey} />}

      <Modal open={showKeyModal} title='Admin key required' footer={null} closable={false}>
        <Space direction='vertical' style={{ width: '100%' }}>
          <Input.Password
            placeholder='Enter admin key'
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
          />
          <Button type='primary' onClick={saveKey} disabled={!adminKey}>
            Continue
          </Button>
        </Space>
      </Modal>
    </Card>
  )
}

export default AdminPanel
