import { useState } from 'react'
import { Button, Card, Input, Space, Table, message, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'

type UnverifiedPlayer = {
  id: number
  name: string
  birthdate: string
  sport: string
  verified: boolean
}

const AdminPlayers = () => {
  const [adminKey, setAdminKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<UnverifiedPlayer[]>([])

  const load = async () => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    setLoading(true)
    try {
      const res = await fetch('/admin/unverified-players', {
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed to fetch')
      const json = await res.json()
      setData(json)
    } catch {
      message.error('Failed to load unverified players')
    } finally {
      setLoading(false)
    }
  }

  const verify = async (id: number) => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/unverified-players/${id}/verify`, {
        method: 'POST',
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed')
      message.success('Player verified')
      setData((prev) => prev.filter((p) => p.id !== id))
    } catch {
      message.error('Failed to verify')
    }
  }

  const columns: ColumnsType<UnverifiedPlayer> = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'DOB', dataIndex: 'birthdate', key: 'birthdate' },
    { title: 'Sport', dataIndex: 'sport', key: 'sport', render: (v) => <Tag>{v}</Tag> },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Button type='primary' size='small' onClick={() => verify(record.id)}>
          Verify
        </Button>
      ),
    },
  ]

  return (
    <Card title='Unverified Players'>
      <Space direction='vertical' style={{ width: '100%' }} size='middle'>
        <Space>
          <Input.Password
            placeholder='Admin key'
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            style={{ minWidth: 280 }}
          />
          <Button onClick={load} loading={loading}>
            Load
          </Button>
        </Space>
        <Table
          rowKey='id'
          columns={columns}
          dataSource={data}
          pagination={{ pageSize: 20 }}
          loading={loading}
        />
      </Space>
    </Card>
  )
}

export default AdminPlayers
