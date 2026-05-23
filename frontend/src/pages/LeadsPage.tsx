import React, { useEffect, useState } from 'react';
import { LeadTable, LeadDetailPanel } from '@/components/leads';
import { useLeadStore, useUIStore } from '@/stores';
import { api } from '@/services';
import type { Lead } from '@/types';
import type { LeadResponse } from '@/services/api';

// Convert backend lead response to frontend Lead type
function mapBackendLead(bl: LeadResponse): Lead {
  // Split contact_full_name into first/last
  const fullName = bl.contact_full_name || '';
  const nameParts = fullName.split(' ');
  const firstName = nameParts[0] || '';
  const lastName = nameParts.slice(1).join(' ') || '';

  return {
    id: bl.id,
    first_name: firstName,
    last_name: lastName,
    email: bl.contact_email || '',
    company: bl.company_name || '',
    title: '', // Not in backend response directly
    phone: undefined,
    linkedin_url: undefined,
    status: mapBackendStatus(bl.status),
    score: bl.lead_score,
    source: bl.score_band || '', // Use score_band as proxy for source
    tags: [],
    last_contacted: bl.last_contacted_at || undefined,
    notes: [],
    custom_fields: {},
    created_at: bl.created_at,
    updated_at: bl.updated_at,
  };
}

function mapBackendStatus(status: string): Lead['status'] {
  const statusMap: Record<string, Lead['status']> = {
    new: 'new',
    contacted: 'contacted',
    qualified: 'qualified',
    proposal: 'proposal',
    negotiation: 'negotiation',
    closed_won: 'closed_won',
    closed_lost: 'closed_lost',
    unreachable: 'unreachable',
    suppressed: 'closed_lost',
    interested: 'qualified',
    not_interested: 'closed_lost',
    // Add more mappings as needed
  };
  return statusMap[status] || 'new';
}

export default function LeadsPage() {
  const { leads, setLeads, selectedLead, selectLead } = useLeadStore();
  const { addNotification } = useUIStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadLeads = async () => {
      try {
        const response = await api.leads.list({ per_page: 200 });
        const mappedLeads = response.items.map(mapBackendLead);
        setLeads(mappedLeads);
      } catch (err) {
        addNotification({ type: 'error', message: 'Failed to load leads. Please try again.' });
        console.error('Failed to load leads:', err);
        setLeads([]);
      } finally {
        setLoading(false);
      }
    };
    loadLeads();
  }, [setLeads, addNotification]);

  const handleImport = () => {
    // Create a hidden file input to trigger CSV import
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,.txt';
    input.onchange = async (e: Event) => {
      const target = e.target as HTMLInputElement;
      const file = target.files?.[0];
      if (!file) return;

      try {
        addNotification({ type: 'info', message: 'Importing CSV...' });
        const result = await api.leads.importCsv(file);
        addNotification({
          type: result.errors > 0 ? 'warning' : 'success',
          message: `Import complete: ${result.created} created, ${result.merged} merged, ${result.skipped} skipped`,
        });
        // Reload leads
        const response = await api.leads.list({ per_page: 200 });
        setLeads(response.items.map(mapBackendLead));
      } catch (err) {
        addNotification({ type: 'error', message: 'CSV import failed. Please try again.' });
      }
    };
    input.click();
  };

  return (
    <div className="animate-fade-in">
      <LeadTable
        leads={leads}
        onSelectLead={(lead) => selectLead(lead)}
        onImport={handleImport}
        onCreateNew={() => addNotification({ type: 'info', message: 'Create lead form coming soon' })}
        loading={loading}
      />
      {selectedLead && (
        <LeadDetailPanel
          lead={selectedLead}
          onClose={() => selectLead(null)}
        />
      )}
    </div>
  );
}