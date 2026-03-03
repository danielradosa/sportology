import { useState, useEffect, useCallback, useMemo } from 'react'
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
import * as subscriptionService from '../services/subscriptionService'
import * as authService from '../services/authService'
import { ApiError } from '../services/apiClient'
import { BrowserProvider, Contract, parseUnits } from 'ethers'

const { Title, Text } = Typography

function Dashboard() {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [createLoading, setCreateLoading] = useState(false)

  // subscription
  const [subLoading, setSubLoading] = useState(false)
  const [subStatus, setSubStatus] = useState<subscriptionService.SubscriptionStatus | null>(null)
  const [walletBusy, setWalletBusy] = useState(false)
  const [lastTx, setLastTx] = useState<string | null>(null)

  const { accessToken } = useAuthStore()
  const { user } = useAuth()

  const { isConnected, stats, requestStats, error: wsError } = useWebSocket({
    autoConnect: true,
  })

  const tier = ((subStatus?.plan_tier || user?.plan_tier || 'free') as string).toLowerCase()
  const keyLimit = tier === 'free' ? 1 : tier === 'starter' ? 3 : 'Unlimited'

  const treasuryWallet = subStatus?.treasury_wallet || undefined
  const usdcAddress = ((import.meta as any).env?.VITE_POLYGON_USDC_ADDRESS as string | undefined) ||
    '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359'

  const linkedWallet = subStatus?.wallet_address || user?.wallet_address || null
  const expiresIso = subStatus?.plan_expires_at ?? user?.plan_expires_at ?? null

  const planExpiresText = useMemo(() => {
    if (!expiresIso) return null
    try {
      return new Date(expiresIso).toLocaleString()
    } catch {
      return String(expiresIso)
    }
  }, [expiresIso])

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

  const refreshMe = useCallback(async () => {
    if (!accessToken) return
    try {
      const me = await authService.me(accessToken)
      useAuthStore.setState((s: any) => ({ ...s, user: me }))
    } catch {
      // ignore
    }
  }, [accessToken])

  const fetchSubStatus = useCallback(async () => {
    if (!accessToken) return
    setSubLoading(true)
    try {
      const s = await subscriptionService.status(accessToken)
      setSubStatus(s)
    } catch {
      // ignore
    } finally {
      setSubLoading(false)
    }
  }, [accessToken])

  useEffect(() => {
    fetchApiKeys()
    fetchSubStatus()
  }, [fetchApiKeys, fetchSubStatus])

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

  const ensurePolygon = async (provider: BrowserProvider) => {
    const network = await provider.getNetwork()
    if (Number(network.chainId) !== 137) {
      throw new Error('Please switch your wallet to Polygon (chainId 137)')
    }
  }

  const handleLinkWallet = async () => {
    const token = requireToken()
    if (!token) return

    if (!(window as any).ethereum) {
      message.error('No wallet found (window.ethereum missing)')
      return
    }

    setWalletBusy(true)
    try {
      const provider = new BrowserProvider((window as any).ethereum)
      await ensurePolygon(provider)
      const signer = await provider.getSigner()
      const addr = await signer.getAddress()

      const nonce = await subscriptionService.getNonce(token)
      const sig = await signer.signMessage(nonce.message)

      await subscriptionService.linkWallet(token, addr, sig)
      message.success('Wallet linked')
      await refreshMe()
      await fetchSubStatus()
    } catch (e: any) {
      message.error(e?.message || 'Failed to link wallet')
    } finally {
      setWalletBusy(false)
    }
  }

  const sendUsdc = async (amountUsdc: number) => {
    const token = requireToken()
    if (!token) return

    if (!treasuryWallet) {
      message.error('VITE_TREASURY_WALLET is not configured in the frontend')
      return
    }

    if (!(window as any).ethereum) {
      message.error('No wallet found (window.ethereum missing)')
      return
    }

    setWalletBusy(true)
    try {
      const provider = new BrowserProvider((window as any).ethereum)
      await ensurePolygon(provider)
      const signer = await provider.getSigner()

      // Minimal ERC20 ABI
      const erc20Abi = [
        'function transfer(address to, uint256 value) returns (bool)',
      ]

      const usdc = new Contract(usdcAddress, erc20Abi, signer)
      const value = parseUnits(String(amountUsdc), 6)
      const tx = await usdc.transfer(treasuryWallet, value)
      setLastTx(tx.hash)
      message.loading({ content: 'Transaction sent. Waiting for confirmation…', key: 'txwait', duration: 0 })
      await tx.wait()
      message.success({ content: 'Confirmed. Crediting subscription…', key: 'txwait' })

      await subscriptionService.verifyPayment(token, tx.hash)
      message.success('Subscription updated')
      await refreshMe()
      await fetchSubStatus()
    } catch (e: any) {
      message.error(e?.message || 'Payment failed')
    } finally {
      setWalletBusy(false)
    }
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
    <div className="page-container">
      <Space className="page-stack" direction="vertical" size={16} style={{ width: '100%' }}>
        <Title level={2} style={{ marginBottom: 0 }}>
          <ApiOutlined /> Dashboard
        </Title>

        <Alert
          type='info'
          showIcon
          message={`Current tier: ${tier.toUpperCase()} · API keys: ${apiKeys.filter(k => k.active).length} / ${keyLimit}`}
          description={tier === 'pro' ? 'Pro includes unlimited API keys and a 1000 / day soft cap with fair-use policy.' : undefined}
        />

        <Row gutter={[16, 16]}>
          {/* Left: API keys + stats */}
          <Col xs={24} md={14} lg={14}>
            <Space className="page-stack" direction="vertical" size={16} style={{ width: '100%' }}>
              <Row gutter={[16, 16]}>
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

              <Space wrap>
                <Button type='primary' icon={<ReloadOutlined />} onClick={requestStats} disabled={!isConnected}>
                  Refresh Stats
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchApiKeys} loading={loading}>
                  Refresh API Keys
                </Button>
              </Space>

              {wsError && (
                <Alert
                  type='warning'
                  showIcon
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
            </Space>
          </Col>

          {/* Right: Subscription */}
          <Col xs={24} md={10} lg={10}>
            <Card className="side-card" title="Subscription (USDC on Polygon)">
              <div className="card-stack">
                <Alert
                  type="info"
                  showIcon
                  message={`Tier: ${tier.toUpperCase()}`}
                  description={
                    planExpiresText
                      ? `Expires: ${planExpiresText} (24h grace after expiry)`
                      : tier !== 'free'
                        ? 'No expiry (manual/admin)'
                        : 'No active subscription.'
                  }
                />

                <Space wrap>
                  <Text type="secondary">Linked wallet:</Text>
                  <Text code>{linkedWallet || '—'}</Text>
                  <Button onClick={handleLinkWallet} loading={walletBusy}>
                    {linkedWallet ? 'Relink wallet' : 'Link wallet'}
                  </Button>
                </Space>

                <Space wrap>
                  <Text type="secondary">Treasury:</Text>
                  <Text code>{treasuryWallet || 'NOT SET'}</Text>
                  {treasuryWallet && (
                    <Tooltip title="Copy">
                      <Button
                        size="small"
                        icon={<CopyOutlined />}
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(treasuryWallet)
                            message.success('Copied treasury address')
                          } catch {
                            message.error('Failed to copy')
                          }
                        }}
                      />
                    </Tooltip>
                  )}
                </Space>

                <Space wrap>
                  <Button
                    type="primary"
                    onClick={() => sendUsdc(19)}
                    disabled={!treasuryWallet || !linkedWallet}
                    loading={walletBusy}
                  >
                    Subscribe Starter (19 USDC)
                  </Button>
                  <Button
                    type="primary"
                    onClick={() => sendUsdc(49)}
                    disabled={!treasuryWallet || !linkedWallet}
                    loading={walletBusy}
                  >
                    Subscribe Pro (49 USDC)
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={async () => {
                      await fetchSubStatus()
                      await refreshMe()
                    }}
                    loading={subLoading}
                  >
                    Refresh
                  </Button>
                </Space>

                {lastTx && (
                  <Text type="secondary">Last tx: <Text code>{lastTx}</Text></Text>
                )}

                {!linkedWallet && (
                  <Alert
                    type="warning"
                    showIcon
                    message="Link your wallet first"
                    description="We verify payments by matching the sender address to your linked wallet, then checking the USDC transfer amount (19 or 49) to the treasury wallet."
                  />
                )}
              </div>
            </Card>
          </Col>
        </Row>

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
      </Space>
    </div>
  )
}

export default Dashboard