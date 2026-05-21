import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, Badge, Button, Input, Textarea, Modal } from '@/components/common';
import { useStatusStyles } from '@/hooks';
import type { Lead, LeadStatus } from '@/types';
import { Search, Filter, Plus, Download, Mail, Phone, X, MessageSquare, ChevronRight } from 'lucide-react';
import LinkedInIcon from '../common/LinkedInIcon';

// ── LeadDetailPanel ────────────────────────────────────────────────────────
interface LeadDetailPanelProps {
  lead: Lead;
  onClose: () => void;
}

export function LeadDetailPanel({ lead, onClose }: LeadDetailPanelProps) {
  const { getStatusStyle } = useStatusStyles();
  const style = getStatusStyle(lead.status);

  return (
    <div className="fixed inset-0 z-40 bg-navy-950/60 backdrop-blur-sm flex justify-end" onClick={onClose}>
      <div
        className="w-full max-w-md bg-navy-900 border-l border-navy-700/30 h-full overflow-y-auto animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-navy-50">
              {lead.first_name} {lead.last_name}
            </h2>
            <button onClick={onClose} className="text-navy-400 hover:text-navy-50 transition-colors">
              <X size={20} />
            </button>
          </div>

          <div className="space-y-4">
            <Badge variant={lead.status === 'qualified' || lead.status === 'closed_won' ? 'success' : lead.status === 'closed_lost' || lead.status === 'unreachable' ? 'danger' : lead.status === 'proposal' || lead.status === 'negotiation' ? 'warning' : 'default'} dot>
              {lead.status.replace('_', ' ')}
            </Badge>

            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2 text-navy-300">
                <Mail size={14} />
                <span>{lead.email}</span>
              </div>
              {lead.phone && (
                <div className="flex items-center gap-2 text-navy-300">
                  <Phone size={14} />
                  <span>{lead.phone}</span>
                </div>
              )}
              {lead.linkedin_url && (
                <div className="flex items-center gap-2 text-navy-300">
                  <LinkedInIcon size={14} />
                  <a href={lead.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-gold-400 hover:text-gold-300">
                    LinkedIn Profile
                  </a>
                </div>
              )}
            </div>

            <div className="border-t border-navy-700/30 pt-4 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-navy-400">Company</span>
                <span className="text-navy-100">{lead.company}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-navy-400">Title</span>
                <span className="text-navy-100">{lead.title}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-navy-400">Score</span>
                <span className="text-navy-100 font-semibold">{lead.score}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-navy-400">Source</span>
                <span className="text-navy-100">{lead.source}</span>
              </div>
              {lead.last_contacted && (
                <div className="flex justify-between text-sm">
                  <span className="text-navy-400">Last Contacted</span>
                  <span className="text-navy-100">{new Date(lead.last_contacted).toLocaleDateString()}</span>
                </div>
              )}
            </div>

            {lead.tags.length > 0 && (
              <div className="border-t border-navy-700/30 pt-4">
                <p className="text-xs text-navy-400 mb-2">Tags</p>
                <div className="flex flex-wrap gap-1.5">
                  {lead.tags.map((tag) => (
                    <Badge key={tag} size="sm">{tag}</Badge>
                  ))}
                </div>
              </div>
            )}

            {lead.notes.length > 0 && (
              <div className="border-t border-navy-700/30 pt-4">
                <p className="text-xs text-navy-400 mb-2">Notes</p>
                <div className="space-y-2">
                  {lead.notes.map((note) => (
                    <div key={note.id} className="bg-navy-800/50 rounded-lg p-3">
                      <p className="text-sm text-navy-200">{note.content}</p>
                      <p className="text-xs text-navy-500 mt-1">{note.author} · {new Date(note.created_at).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── LeadTable ────────────────────────────────────────────────────────────
interface LeadTableProps {
  leads: Lead[];
  onSelectLead: (lead: Lead) => void;
  onImport: () => void;
  onCreateNew: () => void;
  loading: boolean;
}

export function LeadTable({ leads, onSelectLead, onImport, onCreateNew, loading }: LeadTableProps) {
  const { getStatusStyle } = useStatusStyles();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<LeadStatus | 'all'>('all');

  const filteredLeads = leads.filter((lead) => {
    const matchesSearch = searchQuery === '' ||
      `${lead.first_name} ${lead.last_name}`.toLowerCase().includes(searchQuery.toLowerCase()) ||
      lead.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      lead.company.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || lead.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const leadStatuses: (LeadStatus | 'all')[] = ['all', 'new', 'contacted', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost', 'unreachable'];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-navy-50">Leads</h2>
          <span className="text-sm text-navy-400">({leads.length})</span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" icon={<Download size={14} />} onClick={onImport}>Import</Button>
          <Button size="sm" icon={<Plus size={14} />} onClick={onCreateNew}>Add Lead</Button>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-navy-400" />
          <input
            type="text"
            placeholder="Search leads..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-navy-800 border border-navy-700/30 rounded-lg text-sm text-navy-100 placeholder-navy-500 focus:outline-none focus:border-gold-500/50"
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {leadStatuses.map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                statusFilter === status
                  ? 'bg-gold-500 text-navy-950'
                  : 'bg-navy-800 text-navy-300 hover:bg-navy-700'
              }`}
            >
              {status === 'all' ? 'All' : status.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <Card>
          <div className="animate-pulse space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <div className="h-4 w-32 rounded bg-navy-700/50" />
                <div className="h-4 w-24 rounded bg-navy-700/50" />
                <div className="h-4 w-20 rounded bg-navy-700/50" />
                <div className="h-4 w-16 rounded bg-navy-700/50" />
              </div>
            ))}
          </div>
        </Card>
      ) : filteredLeads.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <MessageSquare size={32} className="mx-auto text-navy-500 mb-3" />
            <p className="text-navy-300">No leads found</p>
            <p className="text-sm text-navy-500 mt-1">Add or import leads to get started</p>
          </div>
        </Card>
      ) : (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-navy-700/30">
                  <th className="text-left text-xs font-medium text-navy-400 uppercase tracking-wider px-4 py-3">Name</th>
                  <th className="text-left text-xs font-medium text-navy-400 uppercase tracking-wider px-4 py-3">Company</th>
                  <th className="text-left text-xs font-medium text-navy-400 uppercase tracking-wider px-4 py-3">Status</th>
                  <th className="text-left text-xs font-medium text-navy-400 uppercase tracking-wider px-4 py-3">Score</th>
                  <th className="text-left text-xs font-medium text-navy-400 uppercase tracking-wider px-4 py-3">Source</th>
                  <th className="w-10 px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-navy-700/20">
                {filteredLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => onSelectLead(lead)}
                    className="hover:bg-navy-800/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-sm font-medium text-navy-100">{lead.first_name} {lead.last_name}</p>
                        <p className="text-xs text-navy-400">{lead.email}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-sm text-navy-200">{lead.company}</p>
                        <p className="text-xs text-navy-500">{lead.title}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={lead.status === 'qualified' || lead.status === 'closed_won' ? 'success' : lead.status === 'closed_lost' || lead.status === 'unreachable' ? 'danger' : lead.status === 'proposal' || lead.status === 'negotiation' ? 'warning' : 'default'}
                        size="sm"
                        dot
                      >
                        {lead.status.replace('_', ' ')}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-medium text-navy-100">{lead.score}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-navy-300">{lead.source}</span>
                    </td>
                    <td className="px-4 py-3">
                      <ChevronRight size={16} className="text-navy-500" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}