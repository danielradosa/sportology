export interface User {
  id: string
  email: string
  created_at: string
  plan_tier?: 'free' | 'starter' | 'pro' | string
  plan_expires_at?: string | null
  wallet_address?: string | null
}

export interface ApiKey {
  id: number
  name: string | null
  api_key: string
  created_at: string
  last_used: string | null
  active: boolean
  request_count: number
}

export interface MatchAnalysisRequest {
  player1_name: string
  player1_birthdate: string
  player2_name: string
  player2_birthdate: string
  match_date: string
  sport: 'tennis' | 'table-tennis'
}

export interface PlayerAnalysis {
  name: string
  life_path: number
  expression: number
  personal_year: number
  score: number
  reasons: string[]
}

export interface MatchAnalysisResponse {
  match_date: string
  sport: string
  universal_year: number
  universal_month: number
  universal_day: number
  player1: PlayerAnalysis
  player2: PlayerAnalysis
  winner_prediction: string
  confidence: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH'
  score_difference: number
  recommendation: string
  bet_size: string
  analysis_summary: string
}

export interface DemoMatchAnalysisResponse extends MatchAnalysisResponse {
  demo?: boolean
  note?: string
  remaining_tries?: number
  used_today?: number
}

export interface RealTimeStats {
  timestamp: string
  daily_requests: number
  total_requests: number
  current_active_users: number
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}
