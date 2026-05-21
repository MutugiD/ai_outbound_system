const API_BASE = '/api/v1';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `API Error: ${response.status}`);
    }

    return response.json();
  }

  // Campaigns
  async getCampaigns() {
    return this.request<import('@/types').Campaign[]>('/campaigns');
  }

  async getCampaign(id: string) {
    return this.request<import('@/types').Campaign>(`/campaigns/${id}`);
  }

  async createCampaign(data: Partial<import('@/types').Campaign>) {
    return this.request<import('@/types').Campaign>('/campaigns', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateCampaign(id: string, data: Partial<import('@/types').Campaign>) {
    return this.request<import('@/types').Campaign>(`/campaigns/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteCampaign(id: string) {
    return this.request<void>(`/campaigns/${id}`, { method: 'DELETE' });
  }

  // Leads
  async getLeads(params?: Record<string, string>) {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return this.request<import('@/types').Lead[]>(`/leads${query}`);
  }

  async getLead(id: string) {
    return this.request<import('@/types').Lead>(`/leads/${id}`);
  }

  async createLead(data: Partial<import('@/types').Lead>) {
    return this.request<import('@/types').Lead>('/leads', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateLead(id: string, data: Partial<import('@/types').Lead>) {
    return this.request<import('@/types').Lead>(`/leads/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteLead(id: string) {
    return this.request<void>(`/leads/${id}`, { method: 'DELETE' });
  }

  async importLeads(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<{ imported: number }>('/leads/import', {
      method: 'POST',
      headers: {},
      body: formData,
    });
  }

  // Lead Lists
  async getLeadLists() {
    return this.request<import('@/types').LeadList[]>('/lead-lists');
  }

  // Agents
  async getAgents() {
    return this.request<import('@/types').Agent[]>('/agents');
  }

  async getAgent(id: string) {
    return this.request<import('@/types').Agent>(`/agents/${id}`);
  }

  async createAgent(data: Partial<import('@/types').Agent>) {
    return this.request<import('@/types').Agent>('/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAgent(id: string, data: Partial<import('@/types').Agent>) {
    return this.request<import('@/types').Agent>(`/agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteAgent(id: string) {
    return this.request<void>(`/agents/${id}`, { method: 'DELETE' });
  }

  // Messages
  async getMessages(campaignId?: string) {
    const query = campaignId ? `?campaign_id=${campaignId}` : '';
    return this.request<import('@/types').Message[]>(`/messages${query}`);
  }

  async getMessageTemplates() {
    return this.request<import('@/types').MessageTemplate[]>('/templates');
  }

  async createMessageTemplate(data: Partial<import('@/types').MessageTemplate>) {
    return this.request<import('@/types').MessageTemplate>('/templates', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Dashboard
  async getDashboardMetrics() {
    return this.request<import('@/types').DashboardMetrics>('/dashboard/metrics');
  }

  async getActivityFeed(limit = 20) {
    return this.request<import('@/types').ActivityFeedItem[]>(`/dashboard/activity?limit=${limit}`);
  }

  async getTimeSeries(metric: string, days = 30) {
    return this.request<import('@/types').TimeSeriesPoint[]>(`/dashboard/timeseries?metric=${metric}&days=${days}`);
  }

  // Analytics
  async getAnalytics(params?: Record<string, string>) {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return this.request<Record<string, unknown>>(`/analytics${query}`);
  }

  // Settings
  async getApiConfig() {
    return this.request<import('@/types').ApiConfig>('/settings/api-config');
  }

  async updateApiConfig(data: Partial<import('@/types').ApiConfig>) {
    return this.request<import('@/types').ApiConfig>('/settings/api-config', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // Pipeline
  async getPipeline() {
    return this.request<import('@/types').PipelineStage[]>('/pipeline');
  }
}

export const api = new ApiClient();
export default api;