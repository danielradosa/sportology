import { Typography, Row, Col, Card, List, Space, Button, Tag } from 'antd'
import {
  ThunderboltOutlined,
  LockOutlined,
  BarChartOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import DemoAnalyzer from '../components/MatchAnalyzer/DemoAnalyzer'

const { Title, Paragraph, Text } = Typography

const features = [
  {
    icon: <ThunderboltOutlined />,
    title: 'Numerology Analysis',
    description: 'Life Path, Personal Year, Universal Cycles, Name Expression',
  },
  {
    icon: <BarChartOutlined />,
    title: 'Match Prediction',
    description: 'Predict winners with confidence scores for 1:1 sports',
  },
  {
    icon: <LockOutlined />,
    title: 'Secure Authentication',
    description: 'JWT sessions and API key-based access',
  },
  {
    icon: <ApiOutlined />,
    title: 'REST API',
    description: 'Simple JSON API for your own apps and tools',
  },
]

function Home() {
  return (
    <Space direction='vertical' size={20} style={{ width: '100%' }}>
      <Card>
        <Title style={{ marginBottom: 6 }}>🔮 SAPI | SPORTOLOGY + API</Title>
        <Paragraph style={{ fontSize: 16, maxWidth: 740, marginBottom: 0 }}>
          Numerology-first matchup analysis for tennis and table-tennis. Enter two opponents and date,
          then get confidence, score spread and sizing guidance in seconds.
        </Paragraph>
      </Card>

      <Card>
        <Space direction='vertical' size={12} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>Membership tiers</Title>
          <Row gutter={[12, 12]}>
            <Col xs={24} md={8}>
              <Card size='small' title='Free'>
                <Text>€0 / month</Text>
                <ul style={{ paddingLeft: 18, marginTop: 8 }}>
                  <li>1 API key</li>
                  <li>10 analyses / day</li>
                </ul>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size='small' title={<Space><span>Starter</span><Tag color='blue'>Recommended</Tag></Space>}>
                <Text strong>€19 / month</Text>
                <ul style={{ paddingLeft: 18, marginTop: 8 }}>
                  <li>3 API keys</li>
                  <li>100 analyses / day</li>
                </ul>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size='small' title='Pro'>
                <Text strong>€49 / month</Text>
                <ul style={{ paddingLeft: 18, marginTop: 8 }}>
                  <li>Unlimited API keys</li>
                  <li>1000 analyses / day soft cap + fair use</li>
                </ul>
              </Card>
            </Col>
          </Row>
          <Space>
            <Button type='primary'>Upgrade (coming soon)</Button>
            <Button>Contact for early access</Button>
          </Space>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <DemoAnalyzer />
        </Col>
        <Col xs={24} xl={8}>
          <Card title='Features'>
            <List
              itemLayout='horizontal'
              dataSource={features}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={<Space style={{ fontSize: 22 }}>{item.icon}</Space>}
                    title={item.title}
                    description={item.description}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

export default Home
