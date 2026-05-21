import { create } from 'zustand';
import type { Agent, AgentStatus } from '@/types';

interface AgentStore {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;
  
  setAgents: (agents: Agent[]) => void;
  selectAgent: (agent: Agent | null) => void;
  addAgent: (agent: Agent) => void;
  updateAgent: (id: string, data: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  updateAgentStatus: (id: string, status: AgentStatus) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAgentStore = create<AgentStore>((set) => ({
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null,

  setAgents: (agents) => set({ agents }),
  selectAgent: (agent) => set({ selectedAgent: agent }),
  addAgent: (agent) => set((state) => ({ agents: [...state.agents, agent] })),
  updateAgent: (id, data) => set((state) => ({
    agents: state.agents.map((a) => a.id === id ? { ...a, ...data } : a),
    selectedAgent: state.selectedAgent?.id === id ? { ...state.selectedAgent, ...data } : state.selectedAgent,
  })),
  removeAgent: (id) => set((state) => ({
    agents: state.agents.filter((a) => a.id !== id),
    selectedAgent: state.selectedAgent?.id === id ? null : state.selectedAgent,
  })),
  updateAgentStatus: (id, status) => set((state) => ({
    agents: state.agents.map((a) => a.id === id ? { ...a, status } : a),
    selectedAgent: state.selectedAgent?.id === id ? { ...state.selectedAgent, status } : state.selectedAgent,
  })),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));