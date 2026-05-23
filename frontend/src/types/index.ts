// Core domain types for the AI Outbound Operating System
// These match the backend API response schemas

// ── Enums / Status types ───────────────────────────────────────────────────

export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived';
export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost' | 'unreachable';
export type AgentStatus = 'idle' | 'running' | 'paused' | 'error';
export type ChannelType = 'email' | 'linkedin' | 'phone' | 'sms' | 'whatsapp';
export type MessageStatus = 'pending' | 'sent' | 'delivered' | 'opened' | 'replied' | 'bounced' | 'failed';

// ── Campaign ───────────────────────────────────────────────────────────────

export interface Campaign {
  id: string;
  team_id: string;
  name: string;
  description: string | null;
  status: string; // maps to CampaignStatus but backend returns string
  goal: string | null;
  tone: string;
  approval_mode: string;
  send_limits: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  // Frontend-only computed field, derived from stats endpoint
  stats?: CampaignStats;
  // Derived from send_limits or stats
  daily_limit?: number;
  start_date?: string;
  end_date?: string | null;
}

export interface CampaignStats {
  total_leads: number;
  contacted: number;
  responded: number;
  qualified: number;
  meetings_booked: number;
  deals_closed: number;
  response_rate: number;
  conversion_rate: number;
}

// ── Lead ───────────────────────────────────────────────────────────────────

export interface Lead {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  company: string;
  title: string;
  phone?: string;
  linkedin_url?: string;
  status: LeadStatus;
  score: number;
  source: string;
  tags: string[];
  last_contacted?: string;
  notes: LeadNote[];
  custom_fields: Record<string, string>;
  created_at: string;
  updated_at: string;
}

// Backend lead response — different shape from the frontend Lead type
// See services/api.ts for the LeadResponse type

// ── Lead Notes ─────────────────────────────────────────────────────────────

export interface LeadNote {
  id: string;
  content: string;
  author: string;
  created_at: string;
}

// ── Agent ──────────────────────────────────────────────────────────────────

export interface Agent {
  id: string;
  name: string;
  type: 'outbound' | 'inbound' | 'sdr' | 'bdr' | 'closer';
  status: AgentStatus;
  model: string;
  system_prompt: string;
  channel: ChannelType[];
  current_campaigns: string[];
  stats: AgentStats;
  config: AgentConfig;
  created_at: string;
  updated_at: string;
}

export interface AgentStats {
  messages_sent: number;
  responses_received: number;
  meetings_booked: number;
  deals_closed: number;
  avg_response_time: number;
  success_rate: number;
}

export interface AgentConfig {
  temperature: number;
  max_tokens: number;
  daily_limit: number;
  follow_up_delay: number;
  max_follow_ups: number;
  working_hours_start: string;
  working_hours_end: string;
  timezone: string;
}

// ── Message ───────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  campaign_id: string;
  lead_id: string;
  agent_id: string;
  channel: ChannelType;
  status: MessageStatus;
  content: string;
  subject?: string;
  sent_at?: string;
  opened_at?: string;
  replied_at?: string;
  created_at: string;
}

export interface MessageTemplate {
  id: string;
  name: string;
  channel: ChannelType;
  subject?: string;
  body: string;
  variables: string[];
  created_at: string;
}

// ── Lead List ──────────────────────────────────────────────────────────────

export interface LeadList {
  id: string;
  name: string;
  description: string;
  lead_count: number;
  source: string;
  created_at: string;
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export interface DashboardMetrics {
  total_leads: number;
  new_leads_today: number;
  hot_leads: number;
  messages_sent: number;
  reply_rate: number;
  interested_replies: number;
  booked_calls: number;
  pipeline_value: number;
  conversion_rate: number;
  top_source: string | null;
  top_campaign: string | null;
  // Frontend-computed / legacy compatibility
  total_campaigns?: number;
  active_campaigns?: number;
  messages_sent_today?: number;
  responses_today?: number;
  meetings_today?: number;
}

export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface ActivityFeedItem {
  id: string;
  type: 'message_sent' | 'reply_received' | 'meeting_booked' | 'deal_closed' | 'lead_added' | 'campaign_started' | 'agent_action';
  description: string;
  timestamp: string;
  metadata?: Record<string, string>;
}

// ── User ───────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'manager' | 'user';
  avatar_url?: string;
}

// ── Config ─────────────────────────────────────────────────────────────────

export interface ApiConfig {
  openai_key_set: boolean;
  resend_key_set: boolean;
  linkedin_connected: boolean;
  twilio_connected: boolean;
  webhook_url?: string;
}

// ── Pipeline ───────────────────────────────────────────────────────────────

export interface PipelineStage {
  id: string;
  name: string;
  count: number;
  leads?: Lead[];
  value?: number;
}

// ── Paginated response (generic) ───────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}