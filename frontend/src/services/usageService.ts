import { apiRequest } from './apiClient'

export type UsageStats = {
  // current quota window
  epoch_used: number
  remaining: number
  limit: number
  reset_time: string
  window?: 'user_epoch_24h' | string

  // overall stats
  this_month: number
  total: number
  tier?: 'free' | 'starter' | 'pro' | string
}

export function getUsageStats(accessToken: string) {
  return apiRequest<UsageStats>('/api/v1/usage-stats', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}
