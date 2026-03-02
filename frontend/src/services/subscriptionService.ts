import { apiRequest } from './apiClient'

export type SubscriptionStatus = {
  plan_tier: string
  plan_expires_at: string | null
  wallet_address: string | null
  prices: { starter_usdc: number; pro_usdc: number }
  chain: 'polygon' | string
}

export async function getNonce(accessToken: string): Promise<{ nonce: string; message: string }> {
  return apiRequest('/api/v1/subscription/nonce', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export async function linkWallet(
  accessToken: string,
  wallet_address: string,
  signature: string,
): Promise<{ wallet_address: string }> {
  return apiRequest('/api/v1/subscription/link-wallet', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ wallet_address, signature }),
  })
}

export async function status(accessToken: string): Promise<SubscriptionStatus> {
  return apiRequest('/api/v1/subscription/status', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export async function verifyPayment(accessToken: string, tx_hash: string): Promise<any> {
  return apiRequest('/api/v1/subscription/verify-payment', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ tx_hash }),
  })
}
