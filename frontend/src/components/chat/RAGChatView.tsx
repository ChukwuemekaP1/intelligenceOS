import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { Conversation, Message, Citation, Source } from '../../types';
import {
  MessageSquare,
  Plus,
  Send,
  Sliders,
  CheckCircle2,
  Trash2,
  Cpu,
  Layers,
  Clock,
  Sparkles,
  X,
  Database,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  FileText,
  Globe,
} from 'lucide-react';

// ─── Knowledge Scope Selector ──────────────────────────────────────────────

/**
 * SCOPE_ALL is a sentinel value meaning the user explicitly chose to search
 * the entire workspace. It is NOT the same as having nothing selected.
 *
 * UI contract:
 *   selectedSourceIds === null            → nothing chosen yet (send blocked)
 *   selectedSourceIds === SCOPE_ALL       → user deliberately chose all workspace
 *   selectedSourceIds is a string[]       → explicit source filter
 */
export const SCOPE_ALL = '__ALL__' as const;
export type KnowledgeScope = typeof SCOPE_ALL | string[];

interface KnowledgeScopeSelectorProps {
  workspaceId: string;
  scope: KnowledgeScope | null;
  onChange: (scope: KnowledgeScope) => void;
}

const SOURCE_TYPE_ICON: Record<string, React.FC<{ className?: string }>> = {
  pdf: ({ className }) => <FileText className={className} />,
  website: ({ className }) => <Globe className={className} />,
  csv: ({ className }) => <Database className={className} />,
  text: ({ className }) => <FileText className={className} />,
  image: ({ className }) => <FileText className={className} />,
};

function SourceIcon({ type, className }: { type: string; className?: string }) {
  const Icon = SOURCE_TYPE_ICON[type] ?? (({ className: cn }) => <FileText className={cn} />);
  return <Icon className={className} />;
}

const KnowledgeScopeSelector: React.FC<KnowledgeScopeSelectorProps> = ({
  workspaceId,
  scope,
  onChange,
}) => {
  const [sources, setSources] = useState<Source[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const indexedSources = sources.filter((s) => s.status === 'completed');

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const data = await api.listSources(workspaceId);
      setSources(data);
    } catch {
      // non-critical — selector degrades gracefully
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggleSource = (id: string) => {
    const currentIds: string[] = scope === SCOPE_ALL
      ? indexedSources.map((s) => s.id)
      : Array.isArray(scope)
      ? scope
      : [];
    const next = currentIds.includes(id)
      ? currentIds.filter((s) => s !== id)
      : [...currentIds, id];
    onChange(next);
  };

  const selectedIds: string[] =
    scope === SCOPE_ALL
      ? indexedSources.map((s) => s.id)
      : Array.isArray(scope)
      ? scope
      : [];

  // Button label
  let label: string;
  if (scope === null) {
    label = 'Select sources';
  } else if (scope === SCOPE_ALL) {
    label = 'Entire workspace';
  } else if (scope.length === 0) {
    label = 'No sources selected';
  } else if (scope.length === indexedSources.length && indexedSources.length > 0) {
    label = 'All sources';
  } else {
    label = `${scope.length} source${scope.length > 1 ? 's' : ''} selected`;
  }

  const buttonStyle =
    scope === null || (Array.isArray(scope) && scope.length === 0)
      ? 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400'
      : 'border-indigo-200 dark:border-indigo-800/60 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300';

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => { load(); setOpen((o) => !o); }}
        className={`flex items-center space-x-2 text-xs px-3 py-1.5 rounded-lg border transition-colors ${buttonStyle}`}
      >
        <Database className="w-3.5 h-3.5" />
        <span className="font-medium">{label}</span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1.5 z-30 w-80 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden">
          {/* Header */}
          <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-700">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-200">
              Knowledge Scope
            </span>
            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
              Choose which sources the model may retrieve from.
            </p>
          </div>

          {/* Entire Workspace option — explicit deliberate choice */}
          <div className="p-1 border-b border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => { onChange(SCOPE_ALL); setOpen(false); }}
              className={`w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                scope === SCOPE_ALL
                  ? 'bg-indigo-50 dark:bg-indigo-950/50 text-indigo-900 dark:text-indigo-200'
                  : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-700 dark:text-slate-300'
              }`}
            >
              <div
                className={`w-4 h-4 flex-shrink-0 rounded border flex items-center justify-center ${
                  scope === SCOPE_ALL
                    ? 'bg-indigo-600 border-indigo-600'
                    : 'border-slate-300 dark:border-slate-600'
                }`}
              >
                {scope === SCOPE_ALL && (
                  <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
                    <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
              <Globe className="w-3.5 h-3.5 flex-shrink-0 text-slate-400 dark:text-slate-500" />
              <div>
                <div className="font-semibold">Entire Workspace</div>
                <div className="text-[10px] text-slate-400">Search all indexed sources</div>
              </div>
            </button>
          </div>

          {/* Individual source list */}
          <div className="max-h-56 overflow-y-auto p-1">
            {loading ? (
              <div className="p-3 text-xs text-slate-400 text-center">Loading sources…</div>
            ) : indexedSources.length === 0 ? (
              <div className="p-3 text-xs text-slate-500 text-center">
                No indexed sources in this workspace yet.
              </div>
            ) : (
              indexedSources.map((s) => {
                const checked = selectedIds.includes(s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => toggleSource(s.id)}
                    className={`w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                      checked
                        ? 'bg-indigo-50 dark:bg-indigo-950/50 text-indigo-900 dark:text-indigo-200'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800/60 text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    <div
                      className={`w-4 h-4 flex-shrink-0 rounded border flex items-center justify-center ${
                        checked
                          ? 'bg-indigo-600 border-indigo-600'
                          : 'border-slate-300 dark:border-slate-600'
                      }`}
                    >
                      {checked && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
                          <path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>
                    <SourceIcon
                      type={s.source_type}
                      className={`w-3.5 h-3.5 flex-shrink-0 ${
                        checked ? 'text-indigo-500' : 'text-slate-400 dark:text-slate-500'
                      }`}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{s.title || s.name}</div>
                      <div className="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-mono">
                        {s.source_type} · {s.chunk_count} chunk{s.chunk_count !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Footer: require-selection warning when nothing chosen */}
          {(scope === null || (Array.isArray(scope) && scope.length === 0)) &&
            indexedSources.length > 0 && (
              <div className="px-3 py-2 border-t border-slate-200 dark:border-slate-700 bg-amber-50 dark:bg-amber-950/30">
                <p className="text-[11px] text-amber-700 dark:text-amber-400 flex items-center space-x-1.5">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>
                    Select at least one source — or choose <strong>Entire Workspace</strong> — to
                    enable retrieval.
                  </span>
                </p>
              </div>
            )}
        </div>
      )}
    </div>
  );
};

// ─── Active scope display badge ─────────────────────────────────────────────

function ActiveScopeBadge({ scope, sources }: { scope: KnowledgeScope | null; sources?: Source[] }) {
  if (scope === null || (Array.isArray(scope) && scope.length === 0)) return null;

  if (scope === SCOPE_ALL) {
    return (
      <div className="px-6 py-1.5 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 flex items-center space-x-1.5">
        <Globe className="w-3 h-3 flex-shrink-0 text-indigo-500" />
        <span>
          <span className="font-semibold text-indigo-600 dark:text-indigo-400">Searching:</span>{' '}
          Entire workspace (all indexed sources)
        </span>
      </div>
    );
  }

  const names = sources
    ? scope.map((id) => {
        const s = sources.find((src) => src.id === id);
        return s ? (s.title || s.name) : id.slice(0, 8);
      })
    : scope.map((id) => id.slice(0, 8));

  return (
    <div className="px-6 py-1.5 bg-slate-50 dark:bg-slate-900/60 border-b border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 flex items-center space-x-1.5 flex-wrap gap-y-1">
      <Database className="w-3 h-3 flex-shrink-0 text-indigo-500" />
      <span className="font-semibold text-indigo-600 dark:text-indigo-400">Using:</span>
      {names.map((n, i) => (
        <span
          key={i}
          className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/50 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded font-medium"
        >
          {n}
        </span>
      ))}
    </div>
  );
}

// ─── Main Chat View ─────────────────────────────────────────────────────────

export const RAGChatView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Retrieval settings
  const [retrievalMode, setRetrievalMode] = useState<'hybrid' | 'semantic'>('hybrid');
  const [topK, setTopK] = useState<number>(5);
  const [enableReranking, setEnableReranking] = useState<boolean>(true);
  const [showConfig, setShowConfig] = useState<boolean>(false);

  // Knowledge scope: null = nothing chosen yet (BLOCKS send), SCOPE_ALL = whole workspace, string[] = explicit filter
  const [scope, setScope] = useState<KnowledgeScope | null>(null);

  // Loaded sources list (used to resolve names in ActiveScopeBadge)
  const [loadedSources, setLoadedSources] = useState<Source[]>([]);

  // Citation inspector
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    if (!currentWorkspace) return;
    try {
      const list = await api.listConversations(currentWorkspace.id);
      setConversations(list);
      if (list.length > 0 && !activeConversation) {
        selectConversation(list[0]);
      }
    } catch (err: any) {
      console.error('Failed to load conversations:', err);
    }
  }, [currentWorkspace?.id]);

  // Keep loadedSources in sync for the ActiveScopeBadge name resolution
  useEffect(() => {
    if (!currentWorkspace) return;
    api.listSources(currentWorkspace.id)
      .then((data) => setLoadedSources(data.filter((s) => s.status === 'completed')))
      .catch(() => {});
  }, [currentWorkspace?.id]);

  const selectConversation = async (conv: Conversation) => {
    if (!currentWorkspace) return;
    try {
      const full = await api.getConversation(currentWorkspace.id, conv.id);
      setActiveConversation(full);
      setMessages(full.messages || []);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleCreateConversation = async () => {
    if (!currentWorkspace) return;
    try {
      const title = `Chat ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      })}`;
      const created = await api.createConversation(currentWorkspace.id, title);
      setConversations([created, ...conversations]);
      setActiveConversation(created);
      setMessages([]);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentWorkspace) return;
    try {
      await api.deleteConversation(currentWorkspace.id, convId);
      const remaining = conversations.filter((c) => c.id !== convId);
      setConversations(remaining);
      if (activeConversation?.id === convId) {
        if (remaining.length > 0) selectConversation(remaining[0]);
        else { setActiveConversation(null); setMessages([]); }
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => { loadConversations(); }, [loadConversations]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  // Resolve source_ids to send to the backend
  const resolvedSourceIds: string[] | undefined = (() => {
    if (scope === SCOPE_ALL) return undefined; // search entire workspace
    if (Array.isArray(scope) && scope.length > 0) return scope;
    return undefined; // shouldn't reach here — send is blocked
  })();

  // Guard: send is only allowed once a scope has been set
  const scopeReady = scope !== null && (scope === SCOPE_ALL || (Array.isArray(scope) && scope.length > 0));

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !inputQuestion.trim() || isSending) return;

    // Hard block: require an explicit scope choice before submitting
    if (!scopeReady) {
      setError('Please select at least one knowledge source — or choose "Entire Workspace" — before asking a question.');
      return;
    }

    let conv = activeConversation;
    if (!conv) {
      try {
        const trimmed = inputQuestion.trim();
        const title = trimmed.length > 40 ? `${trimmed.slice(0, 40)}…` : trimmed;
        conv = await api.createConversation(currentWorkspace.id, title);
        setConversations([conv, ...conversations]);
        setActiveConversation(conv);
      } catch (err: any) {
        setError(`Failed to create conversation: ${err.message}`);
        return;
      }
    }

    const questionText = inputQuestion.trim();
    setInputQuestion('');
    setError(null);

    // Optimistic user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: conv.id,
      role: 'user',
      content: questionText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsSending(true);

    try {
      const assistantMsg = await api.sendMessage(currentWorkspace.id, conv.id, questionText, {
        retrieval_mode: retrievalMode,
        top_k: topK,
        enable_reranking: enableReranking,
        // Only pass source_ids when user has made an explicit per-source selection
        source_ids: resolvedSourceIds,
      });
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setError(err.message || 'RAG response generation failed.');
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
    } finally {
      setIsSending(false);
    }
  };

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to start chatting.
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* ── Left: conversation list ── */}
      <div className="w-72 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col flex-shrink-0 transition-colors">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <button
            onClick={handleCreateConversation}
            className="w-full flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all shadow-md shadow-indigo-600/20"
          >
            <Plus className="w-4 h-4" />
            <span>New Conversation</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider px-2 py-1">
            Conversation History
          </div>
          {conversations.length === 0 ? (
            <div className="text-xs text-slate-400 dark:text-slate-600 p-3 text-center">
              No chats yet.
            </div>
          ) : (
            conversations.map((c) => {
              const isSelected = activeConversation?.id === c.id;
              return (
                <div
                  key={c.id}
                  onClick={() => selectConversation(c)}
                  className={`group flex items-center justify-between p-2.5 rounded-xl cursor-pointer text-xs transition-all ${
                    isSelected
                      ? 'bg-indigo-50 dark:bg-slate-900 text-indigo-700 dark:text-white font-medium border border-indigo-200 dark:border-slate-800 shadow-sm'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-900/40'
                  }`}
                >
                  <div className="flex items-center space-x-2.5 truncate">
                    <MessageSquare
                      className={`w-3.5 h-3.5 flex-shrink-0 ${
                        isSelected
                          ? 'text-indigo-600 dark:text-indigo-400'
                          : 'text-slate-400 dark:text-slate-500'
                      }`}
                    />
                    <span className="truncate">{c.title}</span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(c.id, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded transition-opacity"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Config toggle */}
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40">
          <button
            onClick={() => setShowConfig(!showConfig)}
            className="w-full flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 px-2 py-1.5 rounded-lg hover:bg-slate-200/60 dark:hover:bg-slate-800/60 transition-colors"
          >
            <div className="flex items-center space-x-2">
              <Sliders className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
              <span>RAG Configuration</span>
            </div>
            <span className="text-[10px] uppercase font-mono bg-indigo-50 dark:bg-slate-800 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-200 dark:border-transparent">
              {retrievalMode}
            </span>
          </button>
        </div>
      </div>

      {/* ── Main chat area ── */}
      <div className="flex-1 flex flex-col bg-slate-50/50 dark:bg-slate-950 overflow-hidden relative transition-colors">
        {/* Top bar */}
        <div className="h-14 border-b border-slate-200 dark:border-slate-800 px-6 flex items-center justify-between bg-white/70 dark:bg-slate-950/60 backdrop-blur z-10 gap-3">
          <div className="flex items-center space-x-3 truncate min-w-0">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white truncate">
              {activeConversation ? activeConversation.title : 'New RAG Query Session'}
            </h2>
            <div className="hidden sm:flex items-center space-x-1.5 text-[11px] text-slate-500 dark:text-slate-400 flex-shrink-0">
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                {retrievalMode}
              </span>
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Top-{topK}
              </span>
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                {enableReranking ? 'Rerank ✓' : 'Rerank ✗'}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2 flex-shrink-0">
            {/* ── Knowledge scope selector ── */}
            <KnowledgeScopeSelector
              workspaceId={currentWorkspace.id}
              scope={scope}
              onChange={setScope}
            />
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 flex items-center space-x-1.5 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900/60 px-3 py-1.5 rounded-lg"
            >
              <Sliders className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Tune</span>
            </button>
          </div>
        </div>

        {/* Configuration drawer */}
        {showConfig && (
          <div className="bg-white/95 dark:bg-slate-900/95 border-b border-slate-200 dark:border-slate-800 p-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs z-20 shadow-sm">
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Retrieval Mode
              </label>
              <select
                value={retrievalMode}
                onChange={(e) => setRetrievalMode(e.target.value as 'hybrid' | 'semantic')}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-900 dark:text-white"
              >
                <option value="hybrid">Hybrid (BM25 + Dense Vector)</option>
                <option value="semantic">Pure Semantic (Dense Vector)</option>
              </select>
            </div>

            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Top-K Chunks ({topK})
              </label>
              <input
                type="range"
                min="1"
                max="15"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full accent-indigo-600"
              />
            </div>

            <div className="flex items-center justify-between md:justify-start md:space-x-4 pt-3">
              <label className="text-slate-700 dark:text-slate-300 font-semibold">
                Cross-Encoder Reranking
              </label>
              <input
                type="checkbox"
                checked={enableReranking}
                onChange={(e) => setEnableReranking(e.target.checked)}
                className="w-4 h-4 accent-indigo-600 rounded"
              />
            </div>
          </div>
        )}

        {/* Active knowledge scope indicator — updates immediately on change */}
        <ActiveScopeBadge scope={scope} sources={loadedSources} />

        {/* No-scope warning banner — blocks send */}
        {(scope === null || (Array.isArray(scope) && scope.length === 0)) && (
          <div className="px-6 py-2.5 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800/40 text-xs text-amber-800 dark:text-amber-300 flex items-center space-x-2">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            <span>
              <strong>Select a knowledge source above before asking a question.</strong>{' '}
              Choose specific sources or select{' '}
              <strong>&ldquo;Entire Workspace&rdquo;</strong> to search all indexed documents.
              Sending without a selection is not allowed.
            </span>
          </div>
        )}

        {/* Message thread */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-4 text-slate-500 dark:text-slate-400">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Ask your Knowledge Base
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                Select a source (or the entire workspace) above, then ask a question.
                Answers are grounded in retrieved chunks with citations.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full pt-4 text-left">
                {[
                  'What are the key findings in the uploaded documents?',
                  'What guidelines or rules are defined in the knowledge base?',
                  'What is the role of Redis in the ingestion pipeline?',
                  'What security controls are described in the policy documents?',
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInputQuestion(q)}
                    className="p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs text-slate-700 dark:text-slate-300 transition-colors shadow-sm text-left"
                  >
                    &ldquo;{q}&rdquo;
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={msg.id || i}
                className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-2xl rounded-2xl px-5 py-4 text-sm leading-relaxed shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white rounded-br-none'
                      : 'bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-bl-none shadow-md'
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Citations */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-slate-700/60 space-y-2">
                      <div className="text-[11px] font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider flex items-center space-x-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Sources ({msg.citations.length})</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.citations.map((c, citIdx) => {
                          const displayName = c.source_name || (c as any).title || 'Source';
                          return (
                            <button
                              key={citIdx}
                              onClick={() => setSelectedCitation(c)}
                              className="bg-slate-50 dark:bg-slate-950 hover:bg-indigo-50 dark:hover:bg-indigo-950/80 border border-slate-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-700/60 text-slate-700 dark:text-slate-300 text-xs px-2.5 py-1 rounded-lg flex items-center space-x-1.5 transition-all"
                            >
                              <span className="w-4 h-4 rounded-full bg-indigo-100 dark:bg-indigo-900/80 text-indigo-700 dark:text-indigo-300 text-[10px] flex items-center justify-center font-bold flex-shrink-0">
                                {citIdx + 1}
                              </span>
                              <span className="font-medium truncate max-w-[140px]">
                                {displayName}
                              </span>
                              {c.page_number != null && (
                                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                                  p.{c.page_number}
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Telemetry */}
                  {msg.role === 'assistant' && msg.metadata && (
                    <div className="mt-3 pt-2 text-[10px] text-slate-400 dark:text-slate-500 flex items-center space-x-3 flex-wrap gap-y-1">
                      {msg.metadata.retrieval_latency_ms != null && (
                        <span className="flex items-center space-x-1">
                          <Clock className="w-2.5 h-2.5" />
                          <span>{Math.round(msg.metadata.retrieval_latency_ms)}ms retrieval</span>
                        </span>
                      )}
                      {msg.metadata.chunks_retrieved != null && (
                        <span className="flex items-center space-x-1">
                          <Layers className="w-2.5 h-2.5" />
                          <span>{msg.metadata.chunks_retrieved} chunks retrieved</span>
                        </span>
                      )}
                      {msg.metadata.final_context_count != null && (
                        <span className="flex items-center space-x-1">
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          <span>{msg.metadata.final_context_count} in context</span>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {isSending && (
            <div className="flex items-start">
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-bl-none px-5 py-4 text-xs text-slate-600 dark:text-slate-400 flex items-center space-x-3 shadow-md">
                <Cpu className="w-4 h-4 text-indigo-600 dark:text-indigo-400 animate-spin" />
                <span>
                  Retrieving from{' '}
                  {scope === SCOPE_ALL
                    ? 'all workspace knowledge'
                    : Array.isArray(scope) && scope.length > 0
                    ? `${scope.length} selected source${scope.length > 1 ? 's' : ''}`
                    : 'workspace'}
                  , reranking, generating answer…
                </span>
              </div>
            </div>
          )}

          {error && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
          <form
            onSubmit={handleSendMessage}
            className="flex items-center space-x-3 max-w-4xl mx-auto"
          >
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder={
                !scopeReady
                  ? 'Select a knowledge source above before asking…'
                  : scope === SCOPE_ALL
                  ? 'Ask across the entire workspace…'
                  : Array.isArray(scope)
                  ? `Ask across ${scope.length} selected source${scope.length > 1 ? 's' : ''}…`
                  : 'Ask…'
              }
              disabled={isSending || !scopeReady}
              className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600 focus:border-indigo-500 rounded-xl px-4 py-3 text-sm text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none transition-colors shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={isSending || !inputQuestion.trim() || !scopeReady}
              title={!scopeReady ? 'Select a knowledge source first' : 'Send message'}
              className="bg-indigo-600 hover:bg-indigo-500 text-white p-3 rounded-xl transition-all shadow-md shadow-indigo-600/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* ── Citation inspector modal ── */}
      {selectedCitation && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-2xl p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-4">
              <div>
                <h3 className="font-bold text-slate-900 dark:text-white text-base truncate max-w-md">
                  {selectedCitation.source_name || (selectedCitation as any).title || 'Source'}
                </h3>
                <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-slate-400 mt-0.5 flex-wrap gap-y-1">
                  {selectedCitation.source_type && (
                    <span className="uppercase font-mono">{selectedCitation.source_type}</span>
                  )}
                  {selectedCitation.page_number != null && (
                    <span>Page {selectedCitation.page_number}</span>
                  )}
                  {selectedCitation.chunk_index !== undefined && (
                    <span>Chunk #{selectedCitation.chunk_index}</span>
                  )}
                  {selectedCitation.score != null && (
                    <span>Score: {(selectedCitation.score * 100).toFixed(1)}%</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setSelectedCitation(null)}
                className="text-slate-400 hover:text-slate-900 dark:hover:text-white p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">
                Extracted Source Snippet
              </label>
              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4 rounded-xl text-xs font-mono text-slate-800 dark:text-slate-300 leading-relaxed max-h-80 overflow-y-auto whitespace-pre-wrap">
                {selectedCitation.snippet || 'No snippet available for this citation.'}
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setSelectedCitation(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-semibold text-slate-700 dark:text-white rounded-xl transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RAGChatView;
