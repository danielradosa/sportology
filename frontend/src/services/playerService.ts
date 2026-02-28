import { apiRequest } from './apiClient'

export type PlayerSuggestion = {
  id: number | null
  name: string
  birthdate: string
  sport: string
  country?: string | null
  source?: 'db' | 'wikidata'
}

export function searchPlayers(q: string, sport: string) {
  const url = `/api/v1/players?q=${encodeURIComponent(q)}&sport=${encodeURIComponent(sport || '')}`
  return apiRequest<PlayerSuggestion[]>(url)
}

export type ResolvePlayerResponse = {
  id: number
  name: string
  birthdate: string
  sport: string
  country?: string | null
  updated?: boolean
  created?: boolean
}

export function resolvePlayer(name: string, sport: string) {
  return apiRequest<ResolvePlayerResponse>(`/api/v1/players/resolve`, {
    method: 'POST',
    body: JSON.stringify({ name, sport }),
  })
}
