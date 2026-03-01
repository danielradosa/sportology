import { useEffect, useState } from 'react'
import { Button, Input, Space, Table, message, Tag, Popconfirm, Modal, Select, Switch } from 'antd'
import * as XLSX from 'xlsx'
import type { ColumnsType } from 'antd/es/table'

type UnverifiedPlayer = {
  id: number
  name: string
  birthdate: string
  sport: string
  verified: boolean
}

const AdminPlayers = ({ adminKey: adminKeyProp }: { adminKey?: string }) => {
  const [adminKey, setAdminKey] = useState(() => adminKeyProp || localStorage.getItem('admin_key') || '')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<UnverifiedPlayer[]>([])
  const [editing, setEditing] = useState<UnverifiedPlayer | null>(null)
  const [editName, setEditName] = useState('')
  const [editBirthdate, setEditBirthdate] = useState('')
  const [editSport, setEditSport] = useState('tennis')
  const [editVerified, setEditVerified] = useState(false)

  const [showVerified, setShowVerified] = useState(false)
  const [search, setSearch] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const load = async () => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    setLoading(true)
    try {
      const url = showVerified ? '/admin/players' : '/admin/players?verified=false'
      const res = await fetch(url, {
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed to fetch')
      const json = await res.json()
      setData(json)
    } catch {
      message.error('Failed to load players')
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
      load()
    } catch {
      message.error('Failed to verify')
    }
  }

  const bulkVerify = async () => {
    if (!adminKey || selectedRowKeys.length === 0) return
    await Promise.all(selectedRowKeys.map((id) => verify(Number(id))))
    setSelectedRowKeys([])
  }

  const bulkDelete = async () => {
    if (!adminKey || selectedRowKeys.length === 0) return
    await Promise.all(selectedRowKeys.map((id) => remove(Number(id))))
    setSelectedRowKeys([])
  }

  const exportCSV = () => {
    const rows = filteredData.map((p) => ({
      id: p.id,
      name: p.name,
      birthdate: p.birthdate,
      sport: p.sport,
      verified: p.verified,
    }))
    const header = Object.keys(rows[0] || {}).join(',')
    const body = rows.map((r) => Object.values(r).join(',')).join('\n')
    const csv = header + '\n' + body
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'players.csv'
    link.click()
  }

  const exportXLSX = () => {
    const rows = filteredData.map((p) => ({
      id: p.id,
      name: p.name,
      birthdate: p.birthdate,
      sport: p.sport,
      verified: p.verified,
    }))
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Players')
    XLSX.writeFile(wb, 'players.xlsx')
  }

  const remove = async (id: number) => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/players/${id}`, {
        method: 'DELETE',
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed')
      message.success('Player deleted')
      load()
    } catch {
      message.error('Failed to delete')
    }
  }

  const openEdit = (p: UnverifiedPlayer) => {
    setEditing(p)
    setEditName(p.name)
    setEditBirthdate(p.birthdate)
    setEditSport(p.sport)
    setEditVerified(p.verified)
  }

  const saveEdit = async () => {
    if (!adminKey || !editing) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/players/${editing.id}`, {
        method: 'POST',
        headers: { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editName,
          birthdate: editBirthdate,
          sport: editSport,
          verified: editVerified,
        }),
      })
      if (!res.ok) throw new Error('Failed')
      message.success('Player updated')
      setEditing(null)
      load()
    } catch {
      message.error('Failed to update')
    }
  }

  useEffect(() => {
    if (adminKeyProp && adminKeyProp !== adminKey) {
      setAdminKey(adminKeyProp)
    }
  }, [adminKeyProp])

  useEffect(() => {
    if (adminKey) load()
  }, [showVerified, adminKey])

  const filteredData = data.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase()) || p.birthdate.includes(search)
  )

  const columns: ColumnsType<UnverifiedPlayer> = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    { title: 'DOB', dataIndex: 'birthdate', key: 'birthdate' },
    { title: 'Sport', dataIndex: 'sport', key: 'sport', render: (v) => <Tag>{v}</Tag> },
    { title: 'Verified', dataIndex: 'verified', key: 'verified', render: (v) => (v ? <Tag color='green'>Yes</Tag> : <Tag color='red'>No</Tag>) },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Space>
          {!record.verified && (
            <Button type='primary' size='small' onClick={() => verify(record.id)}>
              Verify
            </Button>
          )}
          <Button size='small' onClick={() => openEdit(record)}>
            Edit
          </Button>
          <Popconfirm title='Delete player?' onConfirm={() => remove(record.id)}>
            <Button size='small' danger>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space direction='vertical' style={{ width: '100%' }} size='middle'>
        <Space>
          <Input.Password
            placeholder='Admin key'
            value={adminKey}
            onChange={(e) => {
              setAdminKey(e.target.value)
              localStorage.setItem('admin_key', e.target.value)
            }}
            style={{ minWidth: 280 }}
          />
          <Button onClick={load} loading={loading}>
            Load
          </Button>
          <Space>
            <span>Show verified</span>
            <Switch checked={showVerified} onChange={(v) => setShowVerified(v)} />
          </Space>
        </Space>
        <Space>
          <Input
            placeholder='Search players'
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ minWidth: 260 }}
          />
          <Button onClick={bulkVerify} disabled={selectedRowKeys.length === 0}>
            Bulk verify
          </Button>
          <Button danger onClick={bulkDelete} disabled={selectedRowKeys.length === 0}>
            Bulk delete
          </Button>
          <Button onClick={exportCSV}>Export CSV</Button>
          <Button onClick={exportXLSX}>Export XLSX</Button>
        </Space>
        <Table
          rowKey='id'
          columns={columns}
          dataSource={filteredData}
          pagination={{ pageSize: 20 }}
          loading={loading}
          rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
        />
      </Space>

      <Modal
        open={!!editing}
        title='Edit player'
        onCancel={() => setEditing(null)}
        onOk={saveEdit}
      >
        <Space direction='vertical' style={{ width: '100%' }}>
          <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder='Name' />
          <Input value={editBirthdate} onChange={(e) => setEditBirthdate(e.target.value)} placeholder='YYYY-MM-DD' />
          <Select value={editSport} onChange={(v) => setEditSport(v)}>
            <Select.Option value='tennis'>tennis</Select.Option>
            <Select.Option value='table-tennis'>table-tennis</Select.Option>
          </Select>
          <Space>
            <span>Verified</span>
            <Switch checked={editVerified} onChange={(v) => setEditVerified(v)} />
          </Space>
        </Space>
      </Modal>
    </div>
  )
}

export default AdminPlayers
