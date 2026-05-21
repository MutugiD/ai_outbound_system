import React, { useEffect, useState } from 'react';
import { CampaignList, CampaignDetail, CreateCampaignModal } from '@/components/campaigns';
import { useCampaignStore, useUIStore } from '@/stores';
import { api } from '@/services';
import type { Campaign } from '@/types';

// Demo campaigns data
const demoCampaigns: Campaign[] = [
  {
    id: '1',
    name: 'Q2 SaaS Outreach - Enterprise',
    status: 'active',
    channel: 'email',
    agent_id: 'agent-1',
    lead_list_ids: ['list-1'],
    message_template_id: 'tmpl-1',
    daily_limit: 100,
    start_date: '2026-05-01',
    stats: { total_leads: 156, contacted: 89, responded: 34, qualified: 18, meetings_booked: 7, deals_closed: 2, response_rate: 0.38, conversion_rate: 0.12 },
    created_at: '2026-04-28T10:00:00Z',
    updated_at: '2026-05-21T08:30:00Z',
  },
  {
    id: '2',
    name: 'LinkedIn SDR Blitz',
    status: 'active',
    channel: 'linkedin',
    agent_id: 'agent-2',
    lead_list_ids: ['list-2'],
    message_template_id: 'tmpl-2',
    daily_limit: 50,
    start_date: '2026-05-10',
    stats: { total_leads: 89, contacted: 45, responded: 12, qualified: 6, meetings_booked: 3, deals_closed: 1, response_rate: 0.27, conversion_rate: 0.08 },
    created_at: '2026-05-08T14:00:00Z',
    updated_at: '2026-05-21T07:15:00Z',
  },
  {
    id: '3',
    name: 'Cold Call Follow-up',
    status: 'paused',
    channel: 'phone',
    agent_id: 'agent-3',
    lead_list_ids: ['list-3'],
    message_template_id: 'tmpl-3',
    daily_limit: 30,
    start_date: '2026-05-05',
    stats: { total_leads: 42, contacted: 28, responded: 8, qualified: 4, meetings_booked: 2, deals_closed: 0, response_rate: 0.29, conversion_rate: 0.0 },
    created_at: '2026-05-03T09:00:00Z',
    updated_at: '2026-05-19T16:45:00Z',
  },
  {
    id: '4',
    name: 'WhatsApp Nurture Sequence',
    status: 'draft',
    channel: 'whatsapp',
    agent_id: 'agent-4',
    lead_list_ids: ['list-4'],
    message_template_id: 'tmpl-4',
    daily_limit: 200,
    start_date: '2026-06-01',
    stats: { total_leads: 0, contacted: 0, responded: 0, qualified: 0, meetings_booked: 0, deals_closed: 0, response_rate: 0, conversion_rate: 0 },
    created_at: '2026-05-20T11:00:00Z',
    updated_at: '2026-05-20T11:00:00Z',
  },
  {
    id: '5',
    name: 'Renewal Campaign - Q1 Customers',
    status: 'completed',
    channel: 'email',
    agent_id: 'agent-1',
    lead_list_ids: ['list-5'],
    message_template_id: 'tmpl-5',
    daily_limit: 150,
    start_date: '2026-01-15',
    end_date: '2026-03-31',
    stats: { total_leads: 210, contacted: 198, responded: 67, qualified: 34, meetings_booked: 15, deals_closed: 8, response_rate: 0.34, conversion_rate: 0.15 },
    created_at: '2026-01-10T10:00:00Z',
    updated_at: '2026-03-31T17:00:00Z',
  },
];

export default function CampaignsPage() {
  const { campaigns, setCampaigns, selectedCampaign, selectCampaign } = useCampaignStore();
  const { addNotification } = useUIStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadCampaigns = async () => {
      try {
        const data = await api.getCampaigns();
        setCampaigns(data);
      } catch {
        setCampaigns(demoCampaigns);
      } finally {
        setLoading(false);
      }
    };
    loadCampaigns();
  }, [setCampaigns]);

  const handleToggleStatus = () => {
    if (!selectedCampaign) return;
    const newStatus = selectedCampaign.status === 'active' ? 'paused' : 'active';
    addNotification({
      type: 'info',
      message: `Campaign ${selectedCampaign.name} ${newStatus === 'active' ? 'started' : 'paused'}`,
    });
  };

  const handleDelete = () => {
    if (!selectedCampaign) return;
    addNotification({
      type: 'warning',
      message: `Campaign ${selectedCampaign.name} deleted`,
    });
    selectCampaign(null);
  };

  if (selectedCampaign) {
    return (
      <div className="animate-fade-in">
        <CampaignDetail
          campaign={selectedCampaign}
          onBack={() => selectCampaign(null)}
          onEdit={() => addNotification({ type: 'info', message: 'Edit mode coming soon' })}
          onToggleStatus={handleToggleStatus}
          onDelete={handleDelete}
        />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <CampaignList
        campaigns={campaigns}
        onSelect={(c) => selectCampaign(c)}
        onCreateNew={() => setShowCreateModal(true)}
        loading={loading}
      />
      <CreateCampaignModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
      />
    </div>
  );
}