import React, { useEffect, useState } from 'react';
import { LeadTable, LeadDetailPanel } from '@/components/leads';
import { useLeadStore, useUIStore } from '@/stores';
import { api } from '@/services';
import type { Lead } from '@/types';

// Demo leads data
const demoLeads: Lead[] = [
  {
    id: '1', first_name: 'Sarah', last_name: 'Kim', email: 'sarah.kim@acmecorp.com',
    company: 'Acme Corp', title: 'VP of Engineering', phone: '+1-555-0101',
    linkedin_url: 'https://linkedin.com/in/sarahkim', status: 'qualified', score: 85,
    source: 'LinkedIn', tags: ['enterprise', 'tech'], last_contacted: '2026-05-20T14:00:00Z',
    notes: [{ id: 'n1', content: 'Very interested in our enterprise plan. Follow up with demo.', author: 'SDR Agent 1', created_at: '2026-05-20T14:30:00Z' }],
    custom_fields: {}, created_at: '2026-05-15T10:00:00Z', updated_at: '2026-05-20T14:30:00Z',
  },
  {
    id: '2', first_name: 'John', last_name: 'Martinez', email: 'jmartinez@techflow.io',
    company: 'Techflow', title: 'CTO', phone: '+1-555-0102', status: 'contacted', score: 78,
    source: 'Cold Email', tags: ['saas', 'startup'], last_contacted: '2026-05-19T09:00:00Z',
    notes: [], custom_fields: {}, created_at: '2026-05-10T08:00:00Z', updated_at: '2026-05-19T09:00:00Z',
  },
  {
    id: '3', first_name: 'Lisa', last_name: 'Wang', email: 'lisa.wang@datasync.com',
    company: 'DataSync', title: 'Head of Product', status: 'proposal', score: 92,
    source: 'Referral', tags: ['data', 'enterprise'], last_contacted: '2026-05-18T16:00:00Z',
    notes: [{ id: 'n2', content: 'Requested custom pricing for 500-seat license.', author: 'SDR Agent 2', created_at: '2026-05-18T17:00:00Z' }],
    custom_fields: {}, created_at: '2026-05-05T12:00:00Z', updated_at: '2026-05-18T17:00:00Z',
  },
  {
    id: '4', first_name: 'David', last_name: 'Chen', email: 'dchen@nextgenai.com',
    company: 'NextGen AI', title: 'CEO', phone: '+1-555-0104', linkedin_url: 'https://linkedin.com/in/davidchen',
    status: 'negotiation', score: 95, source: 'Inbound', tags: ['ai', 'startup', 'high-value'],
    last_contacted: '2026-05-17T11:00:00Z', notes: [], custom_fields: {},
    created_at: '2026-05-01T15:00:00Z', updated_at: '2026-05-17T11:00:00Z',
  },
  {
    id: '5', first_name: 'Emily', last_name: 'Johnson', email: 'emily.j@cloudscale.io',
    company: 'CloudScale Systems', title: 'Director of Ops', status: 'closed_won', score: 98,
    source: 'LinkedIn', tags: ['cloud', 'enterprise', 'closed'], last_contacted: '2026-05-16T10:00:00Z',
    notes: [{ id: 'n3', content: 'Signed $45K ARR deal. Onboarding starts next week.', author: 'Closer Agent', created_at: '2026-05-16T10:30:00Z' }],
    custom_fields: {}, created_at: '2026-04-20T09:00:00Z', updated_at: '2026-05-16T10:30:00Z',
  },
  {
    id: '6', first_name: 'Marcus', last_name: 'Brown', email: 'mbrown@retailpro.com',
    company: 'RetailPro', title: 'VP Sales', status: 'new', score: 62,
    source: 'Web Form', tags: ['retail'], notes: [], custom_fields: {},
    created_at: '2026-05-21T08:00:00Z', updated_at: '2026-05-21T08:00:00Z',
  },
  {
    id: '7', first_name: 'Aisha', last_name: 'Patel', email: 'aisha.p@finops.co',
    company: 'FinOps Co', title: 'COO', phone: '+1-555-0107', status: 'contacted', score: 71,
    source: 'Cold Email', tags: ['fintech'], last_contacted: '2026-05-20T15:00:00Z',
    notes: [], custom_fields: {}, created_at: '2026-05-12T14:00:00Z', updated_at: '2026-05-20T15:00:00Z',
  },
  {
    id: '8', first_name: 'Robert', last_name: 'Taylor', email: 'rtaylor@mediabox.com',
    company: 'MediaBox', title: 'Marketing Director', status: 'closed_lost', score: 45,
    source: 'LinkedIn', tags: ['media'], last_contacted: '2026-05-05T09:00:00Z',
    notes: [{ id: 'n4', content: 'Went with competitor. Budget constraints cited.', author: 'SDR Agent 1', created_at: '2026-05-05T10:00:00Z' }],
    custom_fields: {}, created_at: '2026-04-15T11:00:00Z', updated_at: '2026-05-05T10:00:00Z',
  },
  {
    id: '9', first_name: 'Nina', last_name: 'Santos', email: 'nina.s@healthai.com',
    company: 'HealthAI', title: 'Head of Innovation', status: 'qualified', score: 83,
    source: 'Conference', tags: ['healthcare', 'ai', 'enterprise'], last_contacted: '2026-05-19T13:00:00Z',
    notes: [], custom_fields: {}, created_at: '2026-05-08T16:00:00Z', updated_at: '2026-05-19T13:00:00Z',
  },
  {
    id: '10', first_name: 'Tom', last_name: 'Wilson', email: 'twilson@logistech.io',
    company: 'LogisTech', title: 'CIO', status: 'unreachable', score: 34,
    source: 'Cold Email', tags: ['logistics'], notes: [],
    custom_fields: {}, created_at: '2026-05-18T07:00:00Z', updated_at: '2026-05-20T12:00:00Z',
  },
];

export default function LeadsPage() {
  const { leads, setLeads, selectedLead, selectLead } = useLeadStore();
  const { addNotification } = useUIStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadLeads = async () => {
      try {
        const data = await api.getLeads();
        setLeads(data);
      } catch {
        setLeads(demoLeads);
      } finally {
        setLoading(false);
      }
    };
    loadLeads();
  }, [setLeads]);

  return (
    <div className="animate-fade-in">
      <LeadTable
        leads={leads}
        onSelectLead={(lead) => selectLead(lead)}
        onImport={() => addNotification({ type: 'info', message: 'Import feature coming soon' })}
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