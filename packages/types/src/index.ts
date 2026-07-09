// Shared TypeScript types for GTO Wizard Clone
// Re-export everything from domain modules

export interface HandCell {
  hand: string
  action: string
  frequency: number
  equity?: number
}

export interface RangeResponse {
  range: HandCell[]
  source: string
  combos: number
  tree_node?: TreeNodeData
}

export interface TreeNodeData {
  acting_position: string
  available_actions: ActionOption[]
  pot_size: number
  stack_remaining: number
  context: string
  description?: string
}

export interface ActionOption {
  id: string
  actionBase: string
  label: string
  size?: number
  frequency?: number
}

export interface TreeAction {
  position: string
  action: string
  label: string
  size?: number
}

export interface QuizSpot {
  id: string
  category: string
  difficulty: 'easy' | 'medium' | 'hard'
  description: string
  position: string
  stack_depth: number
  board?: string[]
  hero_cards: string[]
  gto_action: string
  gto_frequency: number
  alternatives: { action: string; frequency: number }[]
}

export type Position = 'UTG' | 'HJ' | 'CO' | 'BTN' | 'SB' | 'BB'
export type Rank = 'A' | 'K' | 'Q' | 'J' | 'T' | '9' | '8' | '7' | '6' | '5' | '4' | '3' | '2'

export interface EquityRequest {
  hero_cards: string[]
  villain_range?: string
  board?: string[]
  num_simulations?: number
  variant?: string
}

export interface EquityResponse {
  hero_equity: number
  villain_equity: number
  tie: number
  num_simulations: number
  time_ms: number
}

export interface ICMRequest {
  stacks: number[]
  prizes: number[]
}

export interface ICMResponse {
  equities: number[]
  total_chips: number
  total_prize_pool: number
}

export interface HandHistoryRecord {
  id: string
  hand_id: string
  site: string
  game_type: string
  stakes: string
  date: string
  players: number
  position: string
  hole_cards: string[]
  board: string[]
  pot: number
  result: string
  ev_loss?: number
}
