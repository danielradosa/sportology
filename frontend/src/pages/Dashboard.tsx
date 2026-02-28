import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Row,
  Col,
  Button,
  Table,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  message,
  Statistic,
  Badge,
  Typography,
  Alert,
  Tooltip,
  Skeleton,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  KeyOutlined,
  ApiOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  CopyOutlined
} from '@ant-design/icons'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth, useAuthStore } from '../hooks/useAuth'
import { ApiKey } from '../types'
import * as apiKeyService from '../services/apiKeyService'
import { ApiError } from '../services/apiClient'

const { Title, Text } = Typography

function Dashboard() {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [createLoading, setCreateLoading] = useState(false)

  const { accessToken } = useAuthStore()
  const { user } = useAuth()

  const { isConnected, stats, requestStats, error: wsError } = useWebSocket({
    autoConnect: true,
  })

  const tier = (user?.plan_tier || 'free').toLowerCase()
  const keyLimit = tier === 'free' ? 1 : tier === 'starter' ? 3 : 'Unlimited'

  const requireToken = useCallback(() => {
    if (!accessToken) {
      message.error('Not authenticated')
      return null
    }
    return accessToken
  }, [accessToken])

  const fetchApiKeys = useCallback(async () => {
    const token = requireToken()
    if (!token) return

    try {
      setLoading(true)
      const keys = await apiKeyService.listApiKeys(token)
      setApiKeys(keys)
    } catch {
      message.error('Failed to fetch API keys')
    } finally {
      setLoading(false)
    }
  }, [requireToken])

  useEffect(() => {
    fetchApiKeys()
  }, [fetchApiKeys])

  const handleCreateApiKey = async (values: { name: string }) => {
    const token = requireToken()
    if (!token) return

    setCreateLoading(true)
    try {
      const newKey = await apiKeyService.createApiKey(token, values.name)
      setApiKeys((prev) => [...prev, newKey])
      message.success('API key created')
      setIsCreateModalOpen(false)
      createForm.resetFields()
    } catch (e) {
      if (e instanceof ApiError) message.error(e.message)
      else message.error('Failed to create API key')
    } finally {
      setCreateLoading(false)
    }
  }

  const handleDeleteApiKey = (id: string) => {
    Modal.confirm({
      title: 'Delete API Key?',
      content: 'This action cannot be undone.',
      onOk: async () => {
        const token = requireToken()
        if (!token) return

        try {
          await apiKeyService.deleteApiKey(token, id)
          setApiKeys((prev) => prev.filter((key) => String(key.id) !== String(id)))
          message.success('API key deleted')
        } catch (e) {
          if (e instanceof ApiError) message.error(e.message)
          else message.error('Failed to delete API key')
        }
      },
    })
  }

  const columns = [
    { title: 'Name', dataIndex: 'name', key: 'name' },
    {
      title: "API Key",
      dataIndex: "api_key",
      key: "api_key",
      render: (apiKey: string) => {
        const masked = `${apiKey.slice(0, 10)}...${apiKey.slice(-6)}`
        return (
          <Space size="small">
            <Text code style={{ fontSize: 12 }}>{masked}</Text>
            <Tooltip title="Copy API key">
              <Button
                size="small"
                type="text"
                icon={<CopyOutlined />}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(apiKey)
                    message.success("API key copied")
                  } catch {
                    message.error("Failed to copy")
                  }
                }}
              />
            </Tooltip>
          </Space>
        )
      },
    },
    {
      title: 'Status',
      dataIndex: 'active',
      key: 'active',
      filters: [
        { text: 'Active', value: 'active' },
        { text: 'Revoked', value: 'revoked' },
      ],
      onFilter: (value: any, record: ApiKey) => (value === 'active' ? record.active : !record.active),
      render: (isActive: boolean) =>
        isActive ? (
          <Tag icon={<CheckCircleOutlined />} color='success'>
            Active
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color='error'>
            Revoked
          </Tag>
        ),
    },
    {
      title: 'Usage',
      dataIndex: 'request_count',
      key: 'request_count',
      sorter: (a: ApiKey, b: ApiKey) => (a.request_count || 0) - (b.request_count || 0),
      render: (count: number) => `${count} requests`,
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      sorter: (a: ApiKey, b: ApiKey) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: ApiKey) => (
        <Space>
          <Button
            danger
            size='small'
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteApiKey(String(record.id))}
          >
            Delete
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={2}>
        <ApiOutlined /> Dashboard
      </Title>

      <Alert
        style={{ marginBottom: 16 }}
        type='info'
        showIcon
        message={`Current tier: ${tier.toUpperCase()} · API keys: ${apiKeys.filter(k => k.active).length} / ${keyLimit}`}
        description={tier === 'pro' ? 'Pro includes unlimited API keys and a 1000/day soft cap with fair-use policy.' : undefined}
      />

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            {loading ? (
              <Skeleton active paragraph={{ rows: 1 }} title={{ width: '40%' }} />
            ) : (
              <Statistic
                title={
                  <Space>
                    <Text>Connection</Text>
                    <Tooltip title='Real-time updates via WebSocket'>
                      <QuestionCircleOutlined />
                    </Tooltip>
                  </Space>
                }
                value={isConnected ? 'Connected' : 'Disconnected'}
                valueStyle={{ color: isConnected ? '#3f8600' : '#cf1322' }}
                prefix={isConnected ? <SyncOutlined spin /> : <CloseCircleOutlined />}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            {loading ? (
              <Skeleton active paragraph={{ rows: 1 }} title={{ width: '40%' }} />
            ) : (
              <Statistic title='Daily Requests' value={stats?.daily_requests || 0} prefix={<ApiOutlined />} />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            {loading ? (
              <Skeleton active paragraph={{ rows: 1 }} title={{ width: '40%' }} />
            ) : (
              <Statistic title='Total Requests' value={stats?.total_requests || 0} prefix={<KeyOutlined />} />
            )}
          </Card>
        </Col>
      </Row>

      <Row style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Space wrap>
            <Button type='primary' icon={<ReloadOutlined />} onClick={requestStats} disabled={!isConnected}>
              Refresh Stats
            </Button>
            <Button icon={<ReloadOutlined />} onClick={fetchApiKeys} loading={loading}>
              Refresh API Keys
            </Button>
          </Space>
        </Col>
      </Row>

      {wsError && (
        <Alert
          type='warning'
          showIcon
          style={{ marginBottom: 16 }}
          message='Realtime connection issue'
          description={wsError}
        />
      )}

      <Card
        title={
          <Space>
            <KeyOutlined />
            <span>API Keys</span>
            <Badge count={apiKeys.length} style={{ backgroundColor: '#1890ff' }} />
          </Space>
        }
        extra={
          <Button type='primary' icon={<PlusOutlined />} onClick={() => setIsCreateModalOpen(true)}>
            Create API Key
          </Button>
        }
      >
        {loading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : apiKeys.length > 0 ? (
          <Table dataSource={apiKeys} columns={columns} rowKey='id' pagination={false} scroll={{ x: 760 }} />
        ) : (
          <Alert
            message='No API Keys'
            description='You have not created any API keys yet.'
            type='info'
            showIcon
            action={<Button type='primary' size='small' onClick={() => setIsCreateModalOpen(true)}>Create first key</Button>}
          />
        )}
      </Card>

      <Modal
        title='Create New API Key'
        open={isCreateModalOpen}
        onCancel={() => setIsCreateModalOpen(false)}
        footer={null}
      >
        <Form form={createForm} layout='vertical' onFinish={handleCreateApiKey}>
          <Form.Item name='name' label='Key Name' rules={[{ required: true, message: 'Please enter a key name' }]}>
            <Input placeholder='e.g., Production key' />
          </Form.Item>
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setIsCreateModalOpen(false)}>Cancel</Button>
              <Button type='primary' htmlType='submit' loading={createLoading}>
                Create
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Dashboard