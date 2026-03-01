import { useEffect, useState } from 'react'
import { Button, Input, Select, Space, Table, message, Popconfirm, Modal } from 'antd'
import * as XLSX from 'xlsx'
import type { ColumnsType } from 'antd/es/table'

type UserRow = {
  id: number
  email: string
  created_at: string
  plan_tier: string
}

const tiers = ['free', 'starter', 'pro']

const AdminUsers = ({ adminKey: adminKeyProp }: { adminKey?: string }) => {
  const [adminKey, setAdminKey] = useState(() => adminKeyProp || localStorage.getItem('admin_key') || '')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<UserRow[]>([])
  const [editing, setEditing] = useState<UserRow | null>(null)
  const [editEmail, setEditEmail] = useState('')
  const [search, setSearch] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const load = async () => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    setLoading(true)
    try {
      const res = await fetch('/admin/users', {
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed to fetch')
      const json = await res.json()
      setData(json)
    } catch {
      message.error('Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  const updateTier = async (id: number, tier: string) => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/users/${id}/tier?tier=${tier}`, {
        method: 'POST',
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed')
      setData((prev) => prev.map((u) => (u.id === id ? { ...u, plan_tier: tier } : u)))
      message.success('Tier updated')
    } catch {
      message.error('Failed to update tier')
    }
  }

  const remove = async (id: number) => {
    if (!adminKey) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/users/${id}`, {
        method: 'DELETE',
        headers: { 'X-Admin-Key': adminKey },
      })
      if (!res.ok) throw new Error('Failed')
      setData((prev) => prev.filter((u) => u.id !== id))
      message.success('User deleted')
    } catch {
      message.error('Failed to delete user')
    }
  }

  const openEdit = (u: UserRow) => {
    setEditing(u)
    setEditEmail(u.email)
  }

  const saveEdit = async () => {
    if (!adminKey || !editing) {
      message.error('Enter admin key')
      return
    }
    try {
      const res = await fetch(`/admin/users/${editing.id}`, {
        method: 'POST',
        headers: { 'X-Admin-Key': adminKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: editEmail }),
      })
      if (!res.ok) throw new Error('Failed')
      setData((prev) => prev.map((u) => (u.id === editing.id ? { ...u, email: editEmail } : u)))
      message.success('Email updated')
      setEditing(null)
    } catch {
      message.error('Failed to update email')
    }
  }

  const bulkDelete = async () => {
    if (!adminKey || selectedRowKeys.length === 0) return
    await Promise.all(selectedRowKeys.map((id) => remove(Number(id))))
    setSelectedRowKeys([])
  }

  const exportCSV = () => {
    const rows = filteredData.map((u) => ({
      id: u.id,
      email: u.email,
      created_at: u.created_at,
      plan_tier: u.plan_tier,
    }))
    const header = Object.keys(rows[0] || {}).join(',')
    const body = rows.map((r) => Object.values(r).join(',')).join('\n')
    const csv = header + '\n' + body
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'users.csv'
    link.click()
  }

  const exportXLSX = () => {
    const rows = filteredData.map((u) => ({
      id: u.id,
      email: u.email,
      created_at: u.created_at,
      plan_tier: u.plan_tier,
    }))
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Users')
    XLSX.writeFile(wb, 'users.xlsx')
  }

  const filteredData = data.filter((u) =>
    u.email.toLowerCase().includes(search.toLowerCase()) || u.plan_tier.includes(search.toLowerCase())
  )

  useEffect(() => {
    if (adminKeyProp && adminKeyProp !== adminKey) {
      setAdminKey(adminKeyProp)
    }
  }, [adminKeyProp])

  useEffect(() => {
    if (adminKey) load()
  }, [adminKey])

  const columns: ColumnsType<UserRow> = [
    { title: 'Email', dataIndex: 'email', key: 'email' },
    { title: 'Created', dataIndex: 'created_at', key: 'created_at' },
    {
      title: 'Tier',
      dataIndex: 'plan_tier',
      key: 'plan_tier',
      render: (value: string, record) => (
        <Select value={value} onChange={(val) => updateTier(record.id, val)} style={{ width: 120 }}>
          {tiers.map((t) => (
            <Select.Option key={t} value={t}>
              {t}
            </Select.Option>
          ))}
        </Select>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button size='small' onClick={() => openEdit(record)}>
            Edit Email
          </Button>
          <Popconfirm title='Delete user?' onConfirm={() => remove(record.id)}>
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
        </Space>
        <Space>
          <Input
            placeholder='Search users'
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ minWidth: 260 }}
          />
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

      <Modal open={!!editing} title='Edit email' onCancel={() => setEditing(null)} onOk={saveEdit}>
        <Input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} placeholder='Email' />
      </Modal>
    </div>
  )
}

export default AdminUsers
