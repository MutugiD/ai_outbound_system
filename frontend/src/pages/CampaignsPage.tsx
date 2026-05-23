import React, { useEffect, useState } from 'react';
import { CampaignList, CampaignDetail, CreateCampaignModal } from '@/components/campaigns';
import { useCampaignStore, useUIStore } from '@/stores';
import { api } from '@/services';
import type { Campaign, PaginatedResponse } from '@/types';
import type { CampaignResponse } from '@/services/api';

// Convert backend campaign response to frontend Campaign type
function mapBackendCampaign(bc: CampaignResponse): Campaign {
  return {
    id: bc.id,
    team_id: bc.team_id,
    name: bc.name,
    description: bc.description,
    status: bc.status as Campaign['status'],
    goal: bc.goal,
    tone: bc.tone,
    approval_mode: bc.approval_mode,
    send_limits: bc.send_limits,
    created_by: bc.created_by,
    created_at: bc.created_at,
    updated_at: bc.updated_at,
    // Stats will be populated separately or default to zeros
    stats: {
      total_leads: 0,
      contacted: 0,
      responded: 0,
      qualified: 0,
      meetings_booked: 0,
      deals_closed: 0,
      response_rate: 0,
      conversion_rate: 0,
    },
  };
}

export default function CampaignsPage() {
  const { campaigns, setCampaigns, selectedCampaign, selectCampaign } = useCampaignStore();
  const { addNotification } = useUIStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadCampaigns = async () => {
      try {
        const response = await api.campaigns.list({ per_page: 200 });
        const mappedCampaigns = response.items.map(mapBackendCampaign);

        // Try to fetch stats for each campaign in parallel
        const campaignsStats = await Promise.allSettled(
          mappedCampaigns.map(async (c) => {
            try {
              const stats = await api.campaigns.stats(c.id);
              return {
                ...c,
                stats: {
                  total_leads: stats.enrolled,
                  contacted: stats.messages_sent,
                  responded: Math.round(stats.messages_sent * stats.reply_rate),
                  qualified: Math.round(stats.messages_sent * stats.positive_reply_rate),
                  meetings_booked: stats.booked_calls,
                  deals_closed: 0,
                  response_rate: stats.reply_rate,
                  conversion_rate: stats.bounce_rate > 0 ? stats.positive_reply_rate : 0,
                },
              };
            } catch {
              return c;
            }
          })
        );

        const finalCampaigns = campaignsStats.map((result, idx) =>
          result.status === 'fulfilled' ? result.value : mappedCampaigns[idx]
        );

        setCampaigns(finalCampaigns as Campaign[]);
      } catch (err) {
        addNotification({ type: 'error', message: 'Failed to load campaigns. Please try again.' });
        console.error('Failed to load campaigns:', err);
        setCampaigns([]);
      } finally {
        setLoading(false);
      }
    };
    loadCampaigns();
  }, [setCampaigns, addNotification]);

  const handleToggleStatus = async () => {
    if (!selectedCampaign) return;
    try {
      if (selectedCampaign.status === 'active') {
        await api.campaigns.pause(selectedCampaign.id);
        addNotification({ type: 'success', message: `Campaign "${selectedCampaign.name}" paused` });
      } else {
        await api.campaigns.start(selectedCampaign.id);
        addNotification({ type: 'success', message: `Campaign "${selectedCampaign.name}" started` });
      }
      // Reload campaigns
      const response = await api.campaigns.list({ per_page: 200 });
      setCampaigns(response.items.map(mapBackendCampaign));
    } catch (err) {
      addNotification({ type: 'error', message: 'Failed to update campaign status.' });
    }
  };

  const handleDelete = async () => {
    if (!selectedCampaign) return;
    try {
      await api.campaigns.delete(selectedCampaign.id);
      addNotification({ type: 'warning', message: `Campaign "${selectedCampaign.name}" deleted` });
      selectCampaign(null);
      // Reload
      const response = await api.campaigns.list({ per_page: 200 });
      setCampaigns(response.items.map(mapBackendCampaign));
    } catch (err) {
      addNotification({ type: 'error', message: 'Failed to delete campaign.' });
    }
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