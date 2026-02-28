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
} from "antd"
import { InfoCircleOutlined, DotChartOutlined, CaretUpOutlined } from "@ant-design/icons"
import dayjs from "dayjs"
import { Link } from 'react-router-dom'
import { getLocaleDateFormat } from '../utils/dateFormat'
import { useAuthStore } from "../hooks/useAuth"
import type { ApiKey, MatchAnalysisResponse, MatchAnalysisRequest } from "../types"
import * as apiKeyService from '../services/apiKeyService'
import { analyzeMatch } from '../services/analysisService'
import { searchPlayers, resolvePlayer, type PlayerSuggestion } from '../services/playerService'
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
    const { accessToken } = useAuthStore()
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
    const [p2BirthLocked, setP2BirthLocked] = useState(false)
    const [p1HasDbRecord, setP1HasDbRecord] = useState(false)
    const [p2HasDbRecord, setP2HasDbRecord] = useState(false)
    const [p1NeedsUpdate, setP1NeedsUpdate] = useState(false)
    const [p2NeedsUpdate, setP2NeedsUpdate] = useState(false)

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
                        {p.birthdate}
                        {p.country ? ` • ${p.country}` : ""}
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

            // if updated, keep the button label in mind (UI already shows update state)
        } catch (e: any) {
            message.error('Could not resolve DOB')
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
            message.success("Analysis complete ✅")
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
                                            {!p1BirthLocked && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player1')}>
                                                    {p1HasDbRecord ? 'Fetch DOB' : 'Add Player'}
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
                                            {!p2BirthLocked && (
                                                <Button size="small" type="link" onClick={() => resolveBirthdate('player2')}>
                                                    {p2HasDbRecord ? 'Fetch DOB' : 'Add Player'}
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
                            <Text>Confidence: {String(result.confidence || '').replace('_', ' ')}</Text>
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
        </div>
    )
}