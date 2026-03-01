import { useMemo, useState } from "react"
import {
    Alert,
    Button,
    Card,
    Col,
    Divider,
    Row,
    Space,
    Steps,
    Tag,
    Typography,
    message,
    Collapse,
    Input,
} from "antd"
import {
    ApiOutlined,
    CopyOutlined,
    RocketOutlined,
    SafetyOutlined,
    ThunderboltOutlined,
} from "@ant-design/icons"

const { Title, Text, Paragraph } = Typography

function CodeBlock({
    code,
    language = "bash",
}: {
    code: string
    language?: string
}) {
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(code)
            message.success("Copied ✅")
        } catch {
            message.error("Copy failed 😅")
        }
    }

    return (
        <Card
            size="small"
            style={{ marginTop: 8 }}
            bodyStyle={{ padding: 12 }}
            title={
                <Space>
                    <Tag color="blue">{language}</Tag>
                    <Button size="small" icon={<CopyOutlined />} onClick={copy}>
                        Copy
                    </Button>
                </Space>
            }
        >
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12 }}>
                {code}
            </pre>
        </Card>
    )
}

export default function Bot() {
    const [apiKeyPreview, setApiKeyPreview] = useState("sn_xxx_your_key_here")

    const baseUrl = useMemo(() => {
        // Works locally + Railway
        return window.location.origin
    }, [])

    const curlAnalyze = useMemo(
        () => `curl -s "${baseUrl}/api/v1/analyze-match" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: ${apiKeyPreview}" \\
  -d '{
    "player1_name": "Novak Djokovic",
    "player1_birthdate": "1987-05-22",
    "player2_name": "Carlos Alcaraz",
    "player2_birthdate": "2003-05-05",
    "match_date": "2026-03-01",
    "sport": "tennis"
  }' | jq`,
        [baseUrl, apiKeyPreview]
    )

    const nodeBot = useMemo(
        () => `/**
 * Minimal bot skeleton (Node.js)
 * - Fetch analysis
 * - Decide bet size
 * - Send bet to your bookmaker integration (not included)
 */
import fetch from "node-fetch"

const BASE_URL = "${baseUrl}"
const API_KEY = process.env.SN_API_KEY || "${apiKeyPreview}"

type AnalyzePayload = {
  player1_name: string
  player1_birthdate: string
  player2_name: string
  player2_birthdate: string
  match_date: string
  sport: "tennis" | "table-tennis"
}

async function analyzeMatch(payload: AnalyzePayload) {
  const res = await fetch(\`\${BASE_URL}/api/v1/analyze-match\`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify(payload),
  })

  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

function decideStake(confidence: string) {
  // example risk rules (tweak later)
  if (confidence === "VERY_HIGH") return 0.03
  if (confidence === "HIGH") return 0.015
  if (confidence === "MODERATE") return 0.005
  return 0
}

async function main() {
  const payload: AnalyzePayload = {
    player1_name: "Novak Djokovic",
    player1_birthdate: "1987-05-22",
    player2_name: "Carlos Alcaraz",
    player2_birthdate: "2003-05-05",
    match_date: "2026-03-01",
    sport: "tennis",
  }

  const result = await analyzeMatch(payload)

  console.log("Winner:", result.winner_prediction)
  console.log("Confidence:", result.confidence)
  console.log("Recommendation:", result.recommendation)

  const stakePct = decideStake(result.confidence)
  if (stakePct <= 0) {
    console.log("No bet (low confidence).")
    return
  }

  // TODO: place bet via bookmaker API
  // placeBet({ selection: result.winner_prediction, stakePct })
  console.log(\`Would place bet: \${(stakePct * 100).toFixed(1)}% bankroll\`)
}

main().catch((e) => {
  console.error("Bot error:", e.message)
  process.exit(1)
})`,
        [baseUrl, apiKeyPreview]
    )

    const pythonBot = useMemo(
        () => `"""
Minimal bot skeleton (Python)
- Calls analyze endpoint
- Calculates stake suggestion
- Placeholder for bookmaker integration
"""
import os
import requests

BASE_URL = "${baseUrl}"
API_KEY = os.getenv("SN_API_KEY", "${apiKeyPreview}")

def analyze(payload: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/api/v1/analyze-match",
        json=payload,
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def stake(confidence: str) -> float:
    if confidence == "VERY_HIGH":
        return 0.03
    if confidence == "HIGH":
        return 0.015
    if confidence == "MODERATE":
        return 0.005
    return 0.0

def main():
    payload = {
        "player1_name": "Novak Djokovic",
        "player1_birthdate": "1987-05-22",
        "player2_name": "Carlos Alcaraz",
        "player2_birthdate": "2003-05-05",
        "match_date": "2026-03-01",
        "sport": "tennis",
    }

    result = analyze(payload)
    print("Winner:", result["winner_prediction"])
    print("Confidence:", result["confidence"])
    print("Recommendation:", result["recommendation"])

    pct = stake(result["confidence"])
    if pct <= 0:
        print("No bet (low confidence).")
        return

    # TODO: place bet via bookmaker API
    print(f"Would place bet: {pct*100:.1f}% bankroll")

if __name__ == "__main__":
    main()`,
        [baseUrl, apiKeyPreview]
    )

    const copy = async (txt: string) => {
        try {
            await navigator.clipboard.writeText(txt)
            message.success("Copied ✅")
        } catch {
            message.error("Copy failed 😅")
        }
    }

    return (
        <div className="page-container">
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Title level={2} style={{ marginBottom: 0 }}>
                    <ApiOutlined /> Bot Setup (Coming soon)
                </Title>

                <Alert
                    type="info"
                    showIcon
                    message="The automated betting bot is not released yet"
                    description={
                        <span>
                            This page shows how to integrate your own bot with the API. A
                            “one-click bot” will come later. For now, you plug in your own
                            bookmaker/exchange integration.
                        </span>
                    }
                />

                <Row gutter={16}>
                    <Col xs={24} md={12}>
                        <Card
                            title={
                                <Space>
                                    <RocketOutlined /> Quick Info
                                </Space>
                            }
                        >
                            <Space direction="vertical" style={{ width: "100%" }}>
                                <Text>
                                    <strong>Base URL:</strong>{" "}
                                    <Text code>{baseUrl}</Text>{" "}
                                    <Button size="small" icon={<CopyOutlined />} onClick={() => copy(baseUrl)}>
                                        Copy
                                    </Button>
                                </Text>

                                <Text>
                                    <strong>Analyze endpoint:</strong>{" "}
                                    <Text code>/api/v1/analyze-match</Text>
                                </Text>

                                <Text>
                                    <strong>Auth:</strong>{" "}
                                    <Text code>X-API-Key: sn_...</Text>
                                </Text>

                                <Divider style={{ margin: "12px 0" }} />

                                <Alert
                                    type="warning"
                                    showIcon
                                    message="Risk note"
                                    description="Numerology is not a guarantee. Use small bet sizing and hard limits."
                                />
                            </Space>
                        </Card>
                    </Col>

                    <Col xs={24} md={12}>
                        <Card
                            title={
                                <Space>
                                    <ThunderboltOutlined /> Configure your API key
                                </Space>
                            }
                        >
                            <Paragraph style={{ marginBottom: 8 }}>
                                Put your API key here so the examples on this page render with
                                your key preview (only local UI).
                            </Paragraph>

                            <Space.Compact style={{ width: "100%" }}>
                                <Input
                                    value={apiKeyPreview}
                                    onChange={(e) => setApiKeyPreview(e.target.value)}
                                    placeholder="sn_..."
                                />
                                <Button icon={<CopyOutlined />} onClick={() => copy(apiKeyPreview)}>
                                    Copy
                                </Button>
                            </Space.Compact>

                            <Divider style={{ margin: "12px 0" }} />

                            <Tag color="green">Tip</Tag>{" "}
                            <Text type="secondary">
                                Use <Text code>SN_API_KEY</Text> env var in your bot.
                            </Text>
                        </Card>
                    </Col>
                </Row>

                <Card
                    title={
                        <Space>
                            <SafetyOutlined /> Step-by-step setup
                        </Space>
                    }
                >
                    <Steps
                        direction="vertical"
                        current={1}
                        items={[
                            {
                                title: "Create an API key",
                                description:
                                    "Go to Dashboard → Create API Key. You'll use it as X-API-Key header.",
                            },
                            {
                                title: "Test the API with curl",
                                description:
                                    "Verify you can call /api/v1/analyze-match and get a response.",
                            },
                            {
                                title: "Build your bot loop",
                                description:
                                    "Fetch match schedule from your source, call analyze-match per event, then decide stake.",
                            },
                            {
                                title: "Integrate bookmaker/exchange",
                                description:
                                    "Connect to your bookmaker API and place bets. Add safeguards (limits, cooldowns, max daily loss).",
                            },
                            {
                                title: "Run it safely",
                                description:
                                    "Start with paper trading / simulation, then tiny stakes. Monitor logs & alerts.",
                            },
                        ]}
                    />

                    <Divider />

                    <Text strong>Try it now:</Text>
                    <CodeBlock code={curlAnalyze} language="bash" />
                </Card>

                <Collapse
                    items={[
                        {
                            key: "node",
                            label: "Node.js bot skeleton",
                            children: <CodeBlock code={nodeBot} language="ts" />,
                        },
                        {
                            key: "python",
                            label: "Python bot skeleton",
                            children: <CodeBlock code={pythonBot} language="py" />,
                        },
                        {
                            key: "best-practices",
                            label: "Recommended safeguards (don't skip 🙃)",
                            children: (
                                <Space direction="vertical" size={6} style={{ width: "100%" }}>
                                    <Text>• Daily max loss cap (hard stop)</Text>
                                    <Text>• Max bets per day</Text>
                                    <Text>• Min confidence threshold (e.g. MODERATE+)</Text>
                                    <Text>• Stake sizing by confidence</Text>
                                    <Text>• Logging + alerting (Discord/Telegram/email)</Text>
                                </Space>
                            ),
                        },
                    ]}
                />
            </Space>
        </div>
    )
}