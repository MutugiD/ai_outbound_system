// Core domain types for the AI Outbound Operating System

export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived';
export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost' | 'unreachable';
export type AgentStatus = 'idle' | 'running' | 'paused' | 'error';
export type ChannelType = 'email' | 'linkedin' | 'phone' | 'sms' | 'whatsapp';
export type MessageStatus = 'pending' | 'sent' | 'delivered' | 'opened' | 'replied' | 'bounced' | 'failed';

export interface Campaign {
  id: string;
  name: string;
  status: CampaignStatus;
  channel: ChannelType;
  agent_id: string;
  lead_list_ids: string[];
  message_template_id: string;
  daily_limit: number;
  start_date: string;
  end_date?: string;
  stats: CampaignStats;
  created_at: string;
  updated_at: string;
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

export interface LeadNote {
  id: string;
  content: string;
  author: string;
  created_at: string;
}

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

export interface LeadList {
  id: string;
  name: string;
  description: string;
  lead_count: number;
  source: string;
  created_at: string;
}

export interface DashboardMetrics {
  total_campaigns: number;
  active_campaigns: number;
  total_leads: number;
  messages_sent_today: number;
  responses_today: number;
  meetings_today: number;
  conversion_rate: number;
  reply_rate: number;
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

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'manager' | 'user';
  avatar_url?: string;
}

export interface ApiConfig {
  openai_key_set: boolean;
  resend_key_set: boolean;
  linkedin_connected: boolean;
  twilio_connected: boolean;
  webhook_url?: string;
}

export interface PipelineStage {
  id: string;
  name: string;
  leads: Lead[];
  value: number;
}