/**
 * API Client — connects to the real backend at http://localhost:8001
 *
 * Auth tokens (JWT) are stored in localStorage.
 * Most backend endpoints accept the token via `?Authorization=Bearer <token>`
 * query parameter. Auth endpoints use request bodies.
 */

const API_BASE = 'http://localhost:8001/api/v1';

// ── Token helpers ─────────────────────────────────────────────────────────

function getAccessToken(): string | null {
  return localStorage.getItem('access_token');
}

function getRefreshToken(): string | null {
  return localStorage.getItem('refresh_token');
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
}

function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

// ── Core request ───────────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit & { params?: Record<string, string> } = {},
): Promise<T> {
  const { params = {}, ...fetchOptions } = options;

  // Attach auth token as a query parameter (backend requirement)
  const token = getAccessToken();
  if (token) {
    params['Authorization'] = `Bearer ${token}`;
  }

  const queryString = Object.keys(params).length
    ? '?' + new URLSearchParams(params).toString()
    : '';

  const url = `${API_BASE}${path}${queryString}`;

  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string> ?? {}),
  };

  // Don't set Content-Type for FormData
  if (!(fetchOptions.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  // Handle 401 → attempt refresh
  if (response.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      // Retry with new token
      const newToken = getAccessToken()!;
      const retryParams = { ...params, Authorization: `Bearer ${newToken}` };
      const retryQueryString = Object.keys(retryParams).length
        ? '?' + new URLSearchParams(retryParams).toString()
        : '';
      const retryUrl = `${API_BASE}${path}${retryQueryString}`;

      const retryResponse = await fetch(retryUrl, {
        ...fetchOptions,
        headers: { ...headers },
      });

      if (!retryResponse.ok) {
        const err = await retryResponse.json().catch(() => ({ detail: retryResponse.statusText }));
        throw new ApiError(retryResponse.status, err.detail || `API Error: ${retryResponse.status}`);
      }

      if (retryResponse.status === 204) return undefined as unknown as T;
      return retryResponse.json();
    } else {
      clearTokens();
      throw new ApiError(401, 'Session expired. Please log in again.');
    }
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, err.detail || `API Error: ${response.status}`);
  }

  if (response.status === 204) return undefined as unknown as T;
  return response.json();
}

async function refreshToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });

    if (!res.ok) return false;

    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── Error class ────────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

// ── Paginated response type ───────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// ── Auth ───────────────────────────────────────────────────────────────────

export const auth = {
  register(data: { email: string; password: string; full_name: string; team_name: string }) {
    return request<{ id: string; team_id: string; email: string; full_name: string; role: string }>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify(data) },
    );
  },

  async login(email: string, password: string) {
    const result = await request<{ access_token: string; refresh_token: string; token_type: string; expires_in: number }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
    );
    setTokens(result.access_token, result.refresh_token);
    return result;
  },

  async refresh() {
    return refreshToken();
  },

  me() {
    return request<{ id: string; team_id: string; email: string; full_name: string; role: string; is_active: boolean }>(
      '/auth/me',
    );
  },

  logout() {
    clearTokens();
  },

  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  // Check if user is authenticated
  isAuthenticated(): boolean {
    return !!getAccessToken();
  },
};

// ── Leads ─────────────────────────────────────────────────────────────────

export const leads = {
  list(params?: { page?: number; per_page?: number; status?: string; search?: string; sort_by?: string; sort_order?: string }) {
    const queryParams: Record<string, string> = {};
    if (params) {
      if (params.page) queryParams['page'] = String(params.page);
      if (params.per_page) queryParams['per_page'] = String(params.per_page);
      if (params.status) queryParams['status'] = params.status;
      if (params.search) queryParams['search'] = params.search;
      if (params.sort_by) queryParams['sort_by'] = params.sort_by;
      if (params.sort_order) queryParams['sort_order'] = params.sort_order;
    }
    return request<PaginatedResponse<LeadResponse>>('/leads', { params: queryParams });
  },

  get(id: string) {
    return request<LeadResponse>(`/leads/${id}`);
  },

  create(data: LeadCreateData) {
    return request<LeadResponse>('/leads', { method: 'POST', body: JSON.stringify(data) });
  },

  update(id: string, data: Partial<LeadCreateData>) {
    return request<LeadResponse>(`/leads/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  delete(id: string) {
    return request<void>(`/leads/${id}`, { method: 'DELETE' });
  },

  importCsv(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return request<{ message: string; total: number; created: number; merged: number; skipped: number; errors: number }>(
      '/leads/import-csv',
      { method: 'POST', body: formData },
    );
  },

  transition(leadId: string, data: { to_stage: string; reason?: string; note_content?: string }) {
    return request<void>(`/leads/${leadId}/transition`, { method: 'POST', body: JSON.stringify(data) });
  },
};

// ── Campaigns ──────────────────────────────────────────────────────────────

export const campaigns = {
  list(params?: { status?: string; page?: number; per_page?: number }) {
    const queryParams: Record<string, string> = {};
    if (params) {
      if (params.status) queryParams['status'] = params.status;
      if (params.page) queryParams['page'] = String(params.page);
      if (params.per_page) queryParams['per_page'] = String(params.per_page);
    }
    return request<PaginatedResponse<CampaignResponse>>('/campaigns', { params: queryParams });
  },

  get(id: string) {
    return request<CampaignDetailResponse>(`/campaigns/${id}`);
  },

  create(data: CampaignCreateData) {
    return request<CampaignDetailResponse>('/campaigns', { method: 'POST', body: JSON.stringify(data) });
  },

  update(id: string, data: Partial<CampaignCreateData>) {
    return request<CampaignResponse>(`/campaigns/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  delete(id: string) {
    return request<void>(`/campaigns/${id}`, { method: 'DELETE' });
  },

  start(id: string) {
    return request<CampaignResponse>(`/campaigns/${id}/start`, { method: 'POST' });
  },

  pause(id: string) {
    return request<CampaignResponse>(`/campaigns/${id}/pause`, { method: 'POST' });
  },

  complete(id: string) {
    return request<CampaignResponse>(`/campaigns/${id}/complete`, { method: 'POST' });
  },

  enroll(campaignId: string, leadIds: string[]) {
    return request<unknown>(`/campaigns/${campaignId}/enroll`, {
      method: 'POST',
      body: JSON.stringify({ lead_ids: leadIds }),
    });
  },

  stats(id: string) {
    return request<CampaignStatsResponse>(`/campaigns/${id}/stats`);
  },
};

// ── Outreach ──────────────────────────────────────────────────────────────

export const outreach = {
  generate(data: { lead_id: string; channel?: string; strategies?: string[]; tone?: string; goal?: string }) {
    return request<unknown[]>('/outreach/generate', { method: 'POST', body: JSON.stringify(data) });
  },

  listMessages(params?: { lead_id?: string; campaign_id?: string; status?: string; page?: number }) {
    const queryParams: Record<string, string> = {};
    if (params) {
      if (params.lead_id) queryParams['lead_id'] = params.lead_id;
      if (params.campaign_id) queryParams['campaign_id'] = params.campaign_id;
      if (params.status) queryParams['status'] = params.status;
      if (params.page) queryParams['page'] = String(params.page);
    }
    return request<PaginatedResponse<unknown>>('/outreach/messages', { params: queryParams });
  },

  approveMessage(messageId: string, action: 'approve' | 'reject' = 'approve') {
    return request<unknown>(`/outreach/messages/${messageId}/approve`, {
      method: 'PATCH',
      body: JSON.stringify({ action }),
    });
  },
};

// ── Analytics ─────────────────────────────────────────────────────────────

export const analytics = {
  overview() {
    return request<OverviewStats>('/analytics/overview');
  },

  campaigns(campaignId?: string) {
    const params: Record<string, string> = {};
    if (campaignId) params['campaign_id'] = campaignId;
    return request<CampaignAnalyticsResponse>('/analytics/campaigns', { params });
  },

  pipeline() {
    return request<PipelineAnalyticsResponse>('/analytics/pipeline');
  },

  sources() {
    return request<SourceAnalyticsResponse>('/analytics/sources');
  },

  channels() {
    return request<ChannelAnalyticsResponse>('/analytics/channels');
  },

  scores() {
    return request<ScoreDistributionResponse>('/analytics/scores');
  },

  signals() {
    return request<SignalDistributionResponse>('/analytics/signals');
  },
};

// ── Notes ──────────────────────────────────────────────────────────────────

export const notes = {
  list(leadId: string, params?: { page?: number; note_type?: string }) {
    const queryParams: Record<string, string> = {};
    if (params) {
      if (params.page) queryParams['page'] = String(params.page);
      if (params.note_type) queryParams['note_type'] = params.note_type;
    }
    return request<PaginatedResponse<NoteResponse>>(`/leads/${leadId}/notes`, { params: queryParams });
  },

  create(leadId: string, data: { content: string; note_type?: string }) {
    return request<NoteResponse>(`/leads/${leadId}/notes`, { method: 'POST', body: JSON.stringify(data) });
  },

  update(leadId: string, noteId: string, data: { content?: string; note_type?: string }) {
    return request<NoteResponse>(`/leads/${leadId}/notes/${noteId}`, { method: 'PATCH', body: JSON.stringify(data) });
  },

  delete(leadId: string, noteId: string) {
    return request<void>(`/leads/${leadId}/notes/${noteId}`, { method: 'DELETE' });
  },
};

// ── Contacts ───────────────────────────────────────────────────────────────

export const contacts = {
  get(id: string) {
    return request<ContactDetailResponse>(`/contacts/${id}`);
  },

  update(id: string, data: Record<string, unknown>) {
    return request<ContactResponse>(`/contacts/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  },
};

// ── Response types (matching backend schemas) ─────────────────────────────

export interface LeadResponse {
  id: string;
  team_id: string;
  company_id: string | null;
  contact_id: string | null;
  status: string;
  pipeline_stage: string;
  lead_score: number;
  score_band: string;
  assigned_user_id: string | null;
  last_contacted_at: string | null;
  next_action: string | null;
  next_action_at: string | null;
  created_at: string;
  updated_at: string;
  // Optional fields from LeadDetailResponse
  company_name?: string | null;
  company_domain?: string | null;
  contact_full_name?: string | null;
  contact_email?: string | null;
}

export interface LeadCreateData {
  status?: string;
  pipeline_stage?: string;
  company_name?: string;
  company_domain?: string;
  company_industry?: string;
  contact_first_name?: string;
  contact_last_name?: string;
  contact_email?: string;
  contact_title?: string;
  contact_linkedin_url?: string;
}

export interface CampaignResponse {
  id: string;
  team_id: string;
  name: string;
  description: string | null;
  status: string;
  goal: string | null;
  tone: string;
  approval_mode: string;
  send_limits: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CampaignDetailResponse extends CampaignResponse {
  steps: CampaignStepResponse[];
}

export interface CampaignStepResponse {
  id: string;
  campaign_id: string;
  step_order: number;
  channel: string;
  delay_days: number;
  template_type: string;
  subject_template: string | null;
  body_template: string | null;
  created_at: string;
}

export interface CampaignCreateData {
  name: string;
  description?: string;
  goal?: string;
  tone?: string;
  approval_mode?: string;
  send_limits?: Record<string, unknown>;
  steps?: {
    step_order: number;
    channel?: string;
    delay_days?: number;
    template_type?: string;
    subject_template?: string;
    body_template?: string;
  }[];
}

export interface CampaignStatsResponse {
  campaign_id: string;
  name: string;
  status: string;
  goal: string | null;
  tone: string;
  enrolled: number;
  messages_sent: number;
  open_rate: number;
  reply_rate: number;
  positive_reply_rate: number;
  booked_calls: number;
  bounce_rate: number;
}

export interface OverviewStats {
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
}

export interface CampaignAnalyticsResponse {
  campaigns: {
    campaign_id: string;
    campaign_name: string;
    enrolled: number;
    messages_sent: number;
    open_rate: number;
    reply_rate: number;
    positive_reply_rate: number;
    booked_calls: number;
    bounce_rate: number;
  }[];
}

export interface PipelineAnalyticsResponse {
  stages: { stage: string; count: number }[];
  conversions: { from_stage: string; to_stage: string; rate: number }[];
}

export interface SourceAnalyticsResponse {
  sources: { source: string; leads: number; reply_rate: number; conversion_rate: number }[];
}

export interface ChannelAnalyticsResponse {
  channels: { channel: string; messages: number; reply_rate: number; conversion_rate: number }[];
}

export interface ScoreDistributionResponse {
  distribution: { score_band: string; count: number }[];
}

export interface SignalDistributionResponse {
  signals: { category: string; count: number }[];
}

export interface NoteResponse {
  id: string;
  lead_id: string;
  user_id: string;
  content: string;
  note_type: string;
  created_at: string;
  updated_at: string;
}

export interface ContactResponse {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  title: string | null;
  linkedin_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactDetailResponse extends ContactResponse {
  company_name: string | null;
  company_domain: string | null;
  company_industry: string | null;
}

// ── Default export for backward compatibility ─────────────────────────────

export const api = {
  // Auth
  auth,

  // Resources
  leads,
  campaigns,
  outreach,
  analytics,
  notes,
  contacts,

  // Convenience methods matching the old interface
  getDashboardMetrics: () => analytics.overview(),
  getCampaigns: (params?: { status?: string }) => campaigns.list(params),
  getCampaign: (id: string) => campaigns.get(id),
  createCampaign: (data: CampaignCreateData) => campaigns.create(data),
  updateCampaign: (id: string, data: Partial<CampaignCreateData>) => campaigns.update(id, data),
  deleteCampaign: (id: string) => campaigns.delete(id),

  getLeads: (params?: Record<string, string>) => leads.list(params),
  getLead: (id: string) => leads.get(id),
  createLead: (data: LeadCreateData) => leads.create(data),
  updateLead: (id: string, data: Partial<LeadCreateData>) => leads.update(id, data),
  deleteLead: (id: string) => leads.delete(id),
  importLeads: (file: File) => leads.importCsv(file),

  // Pipeline
  getPipeline: () => analytics.pipeline(),

  // Settings
  getApiConfig: () => Promise.resolve({ openai_key_set: false, resend_key_set: false, linkedin_connected: false, twilio_connected: false }),
  updateApiConfig: () => Promise.resolve({ openai_key_set: false, resend_key_set: false, linkedin_connected: false, twilio_connected: false }),

  // Agents (not yet in backend - stub)
  getAgents: () => Promise.resolve([]),
  getAgent: (id: string) => Promise.resolve(null),
  createAgent: () => Promise.resolve(null),
  updateAgent: () => Promise.resolve(null),
  deleteAgent: () => Promise.resolve(undefined),

  // Messages
  getMessages: (campaignId?: string) => outreach.listMessages(campaignId ? { campaign_id: campaignId } : undefined),
  getMessageTemplates: () => Promise.resolve([]),
  createMessageTemplate: () => Promise.resolve(null),

  // Activity (will be derived from analytics/pipeline for now)
  getActivityFeed: (limit = 20) => Promise.resolve([]),
  getTimeSeries: () => Promise.resolve([]),
  getAnalytics: analytics.overview,
  getLeadLists: () => Promise.resolve([]),
};

export default api;