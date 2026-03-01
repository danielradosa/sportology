import { useEffect, useMemo, useRef, useState } from "react"
import {
    Card,
    Form,
    Input,
    Button,
    DatePicker,
    Select,
    Space,
    Typography,
    message,
    Spin,
    Alert,
    Col,
    Row,
    Divider,
    AutoComplete,
    Progress,
    Grid,
    Tag,
    Table,
} from "antd"
import { InfoCircleOutlined, DotChartOutlined, CaretUpOutlined } from "@ant-design/icons"
import dayjs from "dayjs"
import * as XLSX from 'xlsx'
import { Link } from 'react-router-dom'
import { getLocaleDateFormat } from '../utils/dateFormat'
import { useAuthStore } from "../hooks/useAuth"
import type { ApiKey, MatchAnalysisResponse, MatchAnalysisRequest } from "../types"
import * as apiKeyService from '../services/apiKeyService'
import { analyzeMatch } from '../services/analysisService'
import { searchPlayers, resolvePlayer, addPlayer, type PlayerSuggestion } from '../services/playerService'
import { ApiError } from '../services/apiClient'
import { getUsageStats, type UsageStats } from '../services/usageService'

const { Title, Text } = Typography
const { useBreakpoint } = Grid

type AnalyzeFormValues = {
    apiKey: string
    sport: MatchAnalysisRequest['sport']
    player1_name: string
    player1_birthdate: any
    player2_name: string
    player2_birthdate: any
    match_date: any
}

const sportOptions = [
    { value: "tennis", label: "🎾 Tennis" },
    { value: "table-tennis", label: "🏓 Table Tennis" },
]

export default function Analyzer() {
    const [form] = Form.useForm<AnalyzeFormValues>()
    const accessToken = useAuthStore((s) => s.accessToken)
    const screens = useBreakpoint()
    const isMobile = !screens.md
    const dateFormat = getLocaleDateFormat()

    const [keys, setKeys] = useState<ApiKey[]>([])
    const [keysLoading, setKeysLoading] = useState(true)

    const [loading, setLoading] = useState(false)
    const [result, setResult] = useState<MatchAnalysisResponse | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [usage, setUsage] = useState<UsageStats | null>(null)

    const activeKeys = useMemo(() => keys.filter((k) => k.active), [keys])

    // --- Player search/autocomplete ---
    const [p1Options, setP1Options] = useState<any[]>([])
    const [p2Options, setP2Options] = useState<any[]>([])
    const p1Timer = useRef<number | null>(null)
    const p2Timer = useRef<number | null>(null)

    // --- Birthdate lock state ---
    const [p1BirthLocked, setP1BirthLocked] = useState(false)
    const [history, setHistory] = useState<any[]>([])
    const [historyLoading, setHistoryLoading] = useState(false)
    const [historyQuery, setHistoryQuery] = useState('')
    const [historySport, setHistorySport] = useState('')
    const [historyRange, setHistoryRange] = useState<any>(null)
    const [p2BirthLocked, setP2BirthLocked] = useState(false)
    const [p1HasDbRecord, setP1HasDbRecord] = useState(false)
    const [p2HasDbRecord, setP2HasDbRecord] = useState(false)
    const [p1NeedsUpdate, setP1NeedsUpdate] = useState(false)
    const [p2NeedsUpdate, setP2NeedsUpdate] = useState(false)

    const p1Name = Form.useWatch('player1_name', form)
    const p2Name = Form.useWatch('player2_name', form)
    const p1Birth = Form.useWatch('player1_birthdate', form)
    const p2Birth = Form.useWatch('player2_birthdate', form)

    // Track "selected" name so we can unlock if user edits it
    const p1SelectedNameRef = useRef<string>("")
    const p2SelectedNameRef = useRef<string>("")

    // Load API keys (JWT protected)
    useEffect(() => {
        const loadKeys = async () => {
            setKeysLoading(true)
            try {
                if (!accessToken) throw new Error("Not authenticated")

                const data: ApiKey[] = await apiKeyService.listApiKeys(accessToken)
                setKeys(data)

                const firstActive = data.find((k) => k.active)
                if (firstActive) form.setFieldsValue({ apiKey: firstActive.api_key })
            } catch {
                message.error("Failed to load API keys")
            } finally {
                setKeysLoading(false)
            }
        }

        loadKeys()
    }, [accessToken, form])

    useEffect(() => {
        const loadUsage = async () => {
            if (!accessToken) return
            try {
                const stats = await getUsageStats(accessToken)
                setUsage(stats)
            } catch {
                // non-blocking
            }
        }
        loadUsage()
    }, [accessToken])

    const makeAutocompleteOptions = (players: PlayerSuggestion[]) =>
        players.map((p) => ({
            value: p.name,
            label: (
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>{p.name}</span>
                    <span style={{ opacity: 0.65, fontSize: 12 }}>
                        {p.birthdate ? dayjs(p.birthdate, 'YYYY-MM-DD').format(dateFormat) : ''}
                    </span>
                </div>
            ),
            player: p,
        }))

    const onSearchP1 = (text: string) => {
        const sport = form.getFieldValue("sport") || "tennis"
        if (p1Timer.current) window.clearTimeout(p1Timer.current)
        p1Timer.current = window.setTimeout(async () => {
            const players = await searchPlayers(text, sport)
            setP1Options(makeAutocompleteOptions(players))
        }, 250)
    }

    const onSearchP2 = (text: string) => {
        const sport = form.getFieldValue("sport") || "tennis"
        if (p2Timer.current) window.clearTimeout(p2Timer.current)
        p2Timer.current = window.setTimeout(async () => {
            const players = await searchPlayers(text, sport)
            setP2Options(makeAutocompleteOptions(players))
        }, 250)
    }

    const onSelectP1 = (_value: string, option: any) => {
        const p: PlayerSuggestion | undefined = option?.player
        if (p?.birthdate) {
            form.setFieldsValue({ player1_birthdate: dayjs(p.birthdate, "YYYY-MM-DD") })
            setP1BirthLocked(true)
            p1SelectedNameRef.current = p.name
            setP1HasDbRecord(true)
            setP1NeedsUpdate(false)
        }
    }

    const onSelectP2 = (_value: string, option: any) => {
        const p: PlayerSuggestion | undefined = option?.player
        if (p?.birthdate) {
            form.setFieldsValue({ player2_birthdate: dayjs(p.birthdate, "YYYY-MM-DD") })
            setP2BirthLocked(true)
            p2SelectedNameRef.current = p.name
            setP2HasDbRecord(true)
            setP2NeedsUpdate(false)
        }
    }

    const resolveBirthdate = async (field: 'player1' | 'player2') => {
        const sport = form.getFieldValue('sport') || 'tennis'
        const name = form.getFieldValue(field === 'player1' ? 'player1_name' : 'player2_name')
        if (!name) {
            message.error('Enter a player name first')
            return
        }
        try {
            const res = await resolvePlayer(name, sport)
            const birthdate = dayjs(res.birthdate, 'YYYY-MM-DD')
            if (field === 'player1') {
                form.setFieldsValue({ player1_birthdate: birthdate })
                setP1BirthLocked(true)
                p1SelectedNameRef.current = res.name
                setP1HasDbRecord(true)
                setP1NeedsUpdate(!!res.updated)
            } else {
                form.setFieldsValue({ player2_birthdate: birthdate })
                setP2BirthLocked(true)
                p2SelectedNameRef.current = res.name
                setP2HasDbRecord(true)
                setP2NeedsUpdate(!!res.updated)
            }
            if (res.created) message.success('Player added to database')
            else if (res.updated) message.info('Player updated from Wikidata')
            else message.success('DOB resolved')
        } catch (e: any) {
            message.error('Could not resolve DOB')
        }
    }

    const addManualPlayer = async (field: 'player1' | 'player2') => {
        const sport = form.getFieldValue('sport') || 'tennis'
        const name = form.getFieldValue(field === 'player1' ? 'player1_name' : 'player2_name')
        const birthdateVal = form.getFieldValue(field === 'player1' ? 'player1_birthdate' : 'player2_birthdate')
        if (!name || !birthdateVal) {
            message.error('Enter name and birthdate first')
            return
        }
        try {
            const res = await addPlayer(name, sport, birthdateVal.format('YYYY-MM-DD'))
            if (field === 'player1') {
                setP1HasDbRecord(true)
                setP1NeedsUpdate(false)
                setP1BirthLocked(true)
                p1SelectedNameRef.current = res.name
            } else {
                setP2HasDbRecord(true)
                setP2NeedsUpdate(false)
                setP2BirthLocked(true)
                p2SelectedNameRef.current = res.name
            }
            message.success('Player added to database')
        } catch (e: any) {
            message.error('Could not add player')
        }
    }

    // If user edits name away from selected -> unlock + clear birthdate (avoid wrong birthdate)
    const handlePlayer1NameChange = (val: string) => {
        if (p1BirthLocked && val !== p1SelectedNameRef.current) {
            setP1BirthLocked(false)
            setP1HasDbRecord(false)
            setP1NeedsUpdate(false)
            p1SelectedNameRef.current = ""
            form.setFieldsValue({ player1_birthdate: null })
        }
    }

    const handlePlayer2NameChange = (val: string) => {
        if (p2BirthLocked && val !== p2SelectedNameRef.current) {
            setP2BirthLocked(false)
            setP2HasDbRecord(false)
            setP2NeedsUpdate(false)
            p2SelectedNameRef.current = ""
            form.setFieldsValue({ player2_birthdate: null })
        }
    }

    const onSportChange = () => {
        setP1Options([])
        setP2Options([])

        // sport change invalidates player selection (since DB is sport scoped)
        setP1BirthLocked(false)
        setP2BirthLocked(false)
        setP1HasDbRecord(false)
        setP2HasDbRecord(false)
        p1SelectedNameRef.current = ""
        p2SelectedNameRef.current = ""

        // optional: clear player fields too for safety
        form.setFieldsValue({
            player1_name: "",
            player1_birthdate: null,
            player2_name: "",
            player2_birthdate: null,
        })
    }

    const confidenceBadge = (confidence?: string) => {
        const value = String(confidence || '').replace('_', ' ').toLowerCase()
        if (value.includes('strong')) {
            return <Tag className="confidence-tag confidence-strong">Strong</Tag>
        }
        if (value.includes('moderate')) {
            return <Tag className="confidence-tag confidence-moderate">Moderate</Tag>
        }
        if (value.includes('weak') || value.includes('low')) {
            return <Tag className="confidence-tag confidence-weak">Weak</Tag>
        }
        return value ? <Tag>{value}</Tag> : null
    }

    const loadHistory = async () => {
        if (!accessToken) return
        setHistoryLoading(true)
        try {
            const params = new URLSearchParams()
            if (historyQuery) params.append('q', historyQuery)
            if (historySport) params.append('sport', historySport)
            if (historyRange?.[0]) params.append('start_date', historyRange[0].format('YYYY-MM-DD'))
            if (historyRange?.[1]) params.append('end_date', historyRange[1].format('YYYY-MM-DD'))

            const res = await fetch(`/api/v1/analysis-history?${params.toString()}`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            })
            if (!res.ok) throw new Error('Failed')
            const json = await res.json()
            setHistory(json)
        } catch {
            // ignore
        } finally {
            setHistoryLoading(false)
        }
    }

    useEffect(() => {
        loadHistory()
    }, [accessToken, historyQuery, historySport, historyRange])

    const onFinish = async (values: AnalyzeFormValues) => {
        setLoading(true)
        setError(null)
        setResult(null)

        try {
            const apiKey = values.apiKey
            if (!apiKey) throw new Error("Please select an API key")

            const payload: MatchAnalysisRequest = {
                player1_name: values.player1_name,
                player1_birthdate: values.player1_birthdate.format("YYYY-MM-DD"),
                player2_name: values.player2_name,
                player2_birthdate: values.player2_birthdate.format("YYYY-MM-DD"),
                match_date: values.match_date.format("YYYY-MM-DD"),
                sport: values.sport,
            }

            const data = await analyzeMatch(payload, apiKey)
            setResult(data)
            message.success("Analysis complete")
            if (accessToken) {
                const stats = await getUsageStats(accessToken)
                setUsage(stats)
            }
        } catch (e: any) {
            if (e instanceof ApiError && e.status === 429 && typeof e.details === 'object') {
                const d = e.details as any
                const resetInfo = d?.reset_time ? ` Resets at: ${new Date(d.reset_time).toLocaleString()}.` : ''
                setError((e.message || 'Daily limit reached.') + resetInfo)
            } else {
                setError(e?.message || "Something went wrong")
            }
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
            <Title level={2}><DotChartOutlined /> Match Analyzer</Title>

            {usage && (
                <Card style={{ marginBottom: 12 }}>
                    <Space direction='vertical' style={{ width: '100%' }} size={6}>
                        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                            <Text strong>Daily usage</Text>
                            <Text>{usage.today}/{usage.limit}</Text>
                        </Space>
                        <Progress percent={Math.min(100, Math.round((usage.today / Math.max(1, usage.limit)) * 100))} showInfo={false} />
                        <Text type='secondary'>Resets at {new Date(usage.reset_time).toLocaleString()}</Text>
                    </Space>
                </Card>
            )}

            <Row gutter={[24, 24]}>
                <Col xs={24} lg={16}>
                    <Card>
                        {keysLoading ? (
                            <Spin tip="Loading API keys..." />
                        ) : activeKeys.length === 0 ? (
                    <Alert
                        type="warning"
                        showIcon
                        message="No active API keys"
                        description="Create an API key in the Dashboard first (or re-activate one)."
                        action={<Link to='/dashboard'><Button type='primary' size='small'>Go to Dashboard</Button></Link>}
                    />
                ) : (
                    <Form
                        form={form}
                        layout="vertical"
                        initialValues={{ sport: "tennis", match_date: dayjs() }}
                        onFinish={onFinish}
                        scrollToFirstError
                    >
                        <Form.Item
                            label="API Key"
                            name="apiKey"
                            rules={[{ required: true, message: "Select an API key" }]}
                        >
                            <Select
                                placeholder="Select API key"
                                options={activeKeys.map((k) => ({
                                    value: k.api_key,
                                    label: `${k.name || "Key"} (${k.api_key.slice(0, 8)}...${k.api_key.slice(-4)})`,
                                }))}
                            />
                        </Form.Item>

                        <Form.Item label="Sport" name="sport" rules={[{ required: true }]}>
                            <Select options={sportOptions} onChange={onSportChange} />
                        </Form.Item>

                        <Row gutter={16}>
                            <Col xs={24} md={12}>
                                <Form.Item label="Player 1 Name" name="player1_name" rules={[{ required: true }]}>
                                    <AutoComplete
                                        options={p1Options}
                                        onSearch={onSearchP1}
                                        onSelect={onSelectP1}
                                        onChange={handlePlayer1NameChange}
                                        placeholder="Type to search (e.g. Novak Djokovic)"
                                        filterOption={false}
                                    >
                                        <Input />
                                    </AutoComplete>
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                                <Form.Item
                                    label={
                                        <Space>
                                            Player 1 Birthdate
                                            {p1BirthLocked && <Text type="secondary">(auto-filled)</Text>}
                                            {!p1BirthLocked && !p1HasDbRecord && p1Name && p1Birth && (
                                                <Button size="small" type="link" onClick={() => addManualPlayer('player1')}>
                                                    Save Player
                                                </Button>
                                            )}
                                            {!p1BirthLocked && p1HasDbRecord && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player1')}>
                                                    Fetch DOB
                                                </Button>
                                            )}
                                            {p1HasDbRecord && p1NeedsUpdate && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player1')}>
                                                    Update DOB
                                                </Button>
                                            )}
                                        </Space>
                                    }
                                    name="player1_birthdate"
                                    rules={[{ required: true }]}
                                >
                                    <DatePicker format={dateFormat} inputReadOnly style={{ width: "100%" }} disabled={p1BirthLocked} />
                                </Form.Item>
                            </Col>
                        </Row>

                        <Row gutter={16}>
                            <Col xs={24} md={12}>
                                <Form.Item label="Player 2 Name" name="player2_name" rules={[{ required: true }]}>
                                    <AutoComplete
                                        options={p2Options}
                                        onSearch={onSearchP2}
                                        onSelect={onSelectP2}
                                        onChange={handlePlayer2NameChange}
                                        placeholder="Type to search (e.g. Rafael Nadal)"
                                        filterOption={false}
                                    >
                                        <Input />
                                    </AutoComplete>
                                </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                                <Form.Item
                                    label={
                                        <Space>
                                            Player 2 Birthdate
                                            {p2BirthLocked && <Text type="secondary">(auto-filled)</Text>}
                                            {!p2BirthLocked && !p2HasDbRecord && p2Name && p2Birth && (
                                                <Button size="small" type="link" onClick={() => addManualPlayer('player2')}>
                                                    Save Player
                                                </Button>
                                            )}
                                            {!p2BirthLocked && p2HasDbRecord && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player2')}>
                                                    Fetch DOB
                                                </Button>
                                            )}
                                            {p2HasDbRecord && p2NeedsUpdate && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player2')}>
                                                    Update DOB
                                                </Button>
                                            )}
                                        </Space>
                                    }
                                    name="player2_birthdate"
                                    rules={[{ required: true }]}
                                >
                                    <DatePicker format={dateFormat} inputReadOnly style={{ width: "100%" }} disabled={p2BirthLocked} />
                                </Form.Item>
                            </Col>
                        </Row>

                        <Form.Item label="Match Date" name="match_date" rules={[{ required: true }]}>
                            <DatePicker format={dateFormat} inputReadOnly style={{ width: "100%" }} />
                        </Form.Item>

                        {error && (
                            <Alert style={{ marginBottom: 12 }} type="error" showIcon message="Error" description={error} />
                        )}

                        <div className={isMobile ? 'analyzer-sticky-submit' : ''}>
                            <Button type="primary" htmlType="submit" loading={loading} disabled={activeKeys.length === 0} block={isMobile}>
                                Analyze Match
                            </Button>
                        </div>
                    </Form>
                )}
            </Card>

            {result && (
                <Card style={{ marginTop: 24 }}>
                    <Title level={3} style={{ marginBottom: 16 }}>
                        🏆 Prediction Result
                    </Title>

                    <Card style={{ marginBottom: 16 }} type='inner'>
                        <Space direction='vertical' style={{ width: '100%' }} size={8}>
                            <Text strong style={{ fontSize: 16 }}>Pick: {result.winner_prediction}</Text>
                            <Text>
                                Confidence: {confidenceBadge(result.confidence)}
                            </Text>
                            <Text type='secondary'>Score delta: <CaretUpOutlined /> {result.score_difference}</Text>
                        </Space>
                    </Card>

                    <Row gutter={16} style={{ marginBottom: 16 }}>
                        <Col xs={24} md={12}>
                            <Card bordered title={result.player1?.name || 'Player 1'}>
                                <Text>Total Score: {result.player1?.score}</Text>
                                <Progress percent={Math.min(100, Math.max(0, Number(result.player1?.score || 0)))} showInfo={false} strokeColor='#7a4dd8' />
                                <Divider style={{ margin: '12px 0' }} />
                                <p><strong>Life Path:</strong> {result.player1?.life_path}</p>
                                <p><strong>Expression:</strong> {result.player1?.expression}</p>
                                <p><strong>Personal Year:</strong> {result.player1?.personal_year}</p>
                            </Card>
                        </Col>
                        <Col xs={24} md={12}>
                            <Card bordered title={result.player2?.name || 'Player 2'}>
                                <Text>Total Score: {result.player2?.score}</Text>
                                <Progress percent={Math.min(100, Math.max(0, Number(result.player2?.score || 0)))} showInfo={false} strokeColor='#d6922f' />
                                <Divider style={{ margin: '12px 0' }} />
                                <p><strong>Life Path:</strong> {result.player2?.life_path}</p>
                                <p><strong>Expression:</strong> {result.player2?.expression}</p>
                                <p><strong>Personal Year:</strong> {result.player2?.personal_year}</p>
                            </Card>
                        </Col>
                    </Row>

                    <Card style={{ marginBottom: 16 }} bordered type="inner" title="💰 Betting Recommendation">
                        <p><strong>Suggested Bet Size:</strong> {result.bet_size}</p>
                        <p><strong>Recommendation:</strong> {result.recommendation}</p>
                    </Card>

                    <Card style={{ marginBottom: 16 }} type="inner">
                        <Space align="start">
                            <InfoCircleOutlined style={{ marginTop: 4 }} />
                            <Text>
                                <strong>How scoring works:</strong> Higher total score = more likely to win (numerological alignment for this match date).
                            </Text>
                        </Space>
                    </Card>

                    <Alert
                        type='warning'
                        showIcon
                        style={{ marginBottom: 16 }}
                        message='Risk reminder'
                        description='Numerology is directional, not guaranteed. Use strict bankroll discipline and hard loss limits.'
                    />

                    <Card type="inner" title="📝 Analysis Summary">
                        <Text style={{ whiteSpace: "pre-line" }}>{result.analysis_summary}</Text>
                    </Card>
                </Card>
            )}

                </Col>

                <Col xs={24} lg={8}>
                    <Card style={{ marginTop: 24, position: 'sticky', top: 24 }} title="History">
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Input
                        placeholder="Search players"
                        value={historyQuery}
                        onChange={(e) => setHistoryQuery(e.target.value)}
                    />
                    <DatePicker.RangePicker
                        value={historyRange}
                        onChange={(val) => setHistoryRange(val)}
                        style={{ width: '100%' }}
                    />
                    <Select
                        placeholder="Sport"
                        value={historySport || undefined}
                        onChange={(val) => setHistorySport(val || '')}
                        allowClear
                    >
                        <Select.Option value="tennis">Tennis</Select.Option>
                        <Select.Option value="table-tennis">Table Tennis</Select.Option>
                    </Select>

                    <Space>
                        <Button onClick={() => {
                            const rows = history.map((h) => ({
                                date: h.created_at,
                                player1: h.player1_name,
                                player2: h.player2_name,
                                match_date: h.match_date,
                                confidence: h.confidence,
                                winner_prediction: h.winner_prediction,
                                bet_size: h.bet_size,
                            }))
                            const header = Object.keys(rows[0] || {}).join(',')
                            const body = rows.map((r) => Object.values(r).join(',')).join('\n')
                            const csv = header + '\n' + body
                            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
                            const link = document.createElement('a')
                            link.href = URL.createObjectURL(blob)
                            link.download = 'analysis-history.csv'
                            link.click()
                        }}>
                            Export CSV
                        </Button>
                        <Button onClick={() => {
                            const rows = history.map((h) => ({
                                date: h.created_at,
                                player1: h.player1_name,
                                player2: h.player2_name,
                                match_date: h.match_date,
                                confidence: h.confidence,
                                winner_prediction: h.winner_prediction,
                                bet_size: h.bet_size,
                            }))
                            const ws = XLSX.utils.json_to_sheet(rows)
                            const wb = XLSX.utils.book_new()
                            XLSX.utils.book_append_sheet(wb, ws, 'History')
                            XLSX.writeFile(wb, 'analysis-history.xlsx')
                        }}>
                            Export XLSX
                        </Button>
                    </Space>

                    <Table
                        size="small"
                        rowKey="id"
                        dataSource={history}
                        loading={historyLoading}
                        pagination={{ pageSize: 8 }}
                        columns={[
                            {
                                title: 'Players',
                                render: (r) => (
                                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                                        <span>{r.player1_name}</span>
                                        <span>{r.player2_name}</span>
                                    </div>
                                ),
                            },
                            {
                                title: 'Match',
                                dataIndex: 'match_date',
                                render: (v) => dayjs(v, 'YYYY-MM-DD').format(dateFormat),
                            },
                            {
                                title: 'Conf',
                                dataIndex: 'confidence',
                                render: (v) => confidenceBadge(v),
                            },
                        ]}
                    />
                </Space>
            </Card>
                </Col>
            </Row>
        </div>
    )
}