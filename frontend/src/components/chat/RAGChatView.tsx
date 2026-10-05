import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { Conversation, Message, Citation } from '../../types';
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
} from 'lucide-react';

export const RAGChatView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Retrieval Settings
  const [retrievalMode, setRetrievalMode] = useState<'hybrid' | 'semantic'>('hybrid');
  const [topK, setTopK] = useState<number>(5);
  const [enableReranking, setEnableReranking] = useState<boolean>(true);
  const [showConfig, setShowConfig] = useState<boolean>(false);

  // Selected citation inspector
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadConversations = async () => {
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
  };

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
      const title = `Chat ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
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
        if (remaining.length > 0) {
          selectConversation(remaining[0]);
        } else {
          setActiveConversation(null);
          setMessages([]);
        }
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadConversations();
  }, [currentWorkspace?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !inputQuestion.trim() || isSending) return;

    let conv = activeConversation;
    if (!conv) {
      try {
        const trimmed = inputQuestion?.trim() || 'New Chat';
        const title = trimmed.length > 40 ? `${trimmed.slice(0, 40)}...` : trimmed;
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

    // Optimistically add user message
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
      });

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setError(err.message || 'Failed to complete RAG response generation.');
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
      {/* Left Chat Thread List */}
      <div className="w-72 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col justify-between flex-shrink-0 transition-colors">
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
            <div className="text-xs text-slate-400 dark:text-slate-600 p-3 text-center">No chats yet.</div>
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
                    <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isSelected ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500'}`} />
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

        {/* Quick config toggle at bottom */}
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

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-slate-50/50 dark:bg-slate-950 overflow-hidden relative transition-colors">
        {/* Top Control Bar */}
        <div className="h-14 border-b border-slate-200 dark:border-slate-800 px-6 flex items-center justify-between bg-white/70 dark:bg-slate-950/60 backdrop-blur z-10">
          <div className="flex items-center space-x-3 truncate">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white truncate">
              {activeConversation ? activeConversation.title : 'New RAG Query Session'}
            </h2>
            <div className="hidden sm:flex items-center space-x-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Mode: {retrievalMode}
              </span>
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Top-K: {topK}
              </span>
              <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                Rerank: {enableReranking ? 'Active' : 'Off'}
              </span>
            </div>
          </div>

          <button
            onClick={() => setShowConfig(!showConfig)}
            className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center space-x-1.5 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-900/60 px-3 py-1.5 rounded-lg"
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>Tune Retrieval</span>
          </button>
        </div>

        {/* Configuration Drawer */}
        {showConfig && (
          <div className="bg-white/95 dark:bg-slate-900/95 border-b border-slate-200 dark:border-slate-800 p-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs animate-fadeIn z-20 shadow-sm">
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">Retrieval Mode</label>
              <select
                value={retrievalMode}
                onChange={(e) => setRetrievalMode(e.target.value as any)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-900 dark:text-white"
              >
                <option value="hybrid">Hybrid (BM25 Keyword + Dense Vector)</option>
                <option value="semantic">Pure Semantic Vector Search</option>
              </select>
            </div>

            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">Top-K Chunks ({topK})</label>
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
              <label className="text-slate-700 dark:text-slate-300 font-semibold">Enable Cross-Encoder Reranking</label>
              <input
                type="checkbox"
                checked={enableReranking}
                onChange={(e) => setEnableReranking(e.target.checked)}
                className="w-4 h-4 accent-indigo-600 rounded"
              />
            </div>
          </div>
        )}

        {/* Message Thread */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto space-y-4 text-slate-500 dark:text-slate-400">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Ask your Grounded Knowledge Base</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                Queries are processed with hybrid retrieval, deduplicated, reranked, and synthesized with precise inline citations referencing extracted document chunks.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full pt-4 text-left">
                <button
                  onClick={() => setInputQuestion('What are the key findings and summaries in the uploaded documents?')}
                  className="p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs text-slate-700 dark:text-slate-300 transition-colors shadow-sm"
                >
                  "Summarize key findings in documents"
                </button>
                <button
                  onClick={() => setInputQuestion('What guidelines or rules are defined in the knowledge base?')}
                  className="p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs text-slate-700 dark:text-slate-300 transition-colors shadow-sm"
                >
                  "Explain core guidelines & constraints"
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={msg.id || i}
                className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-2xl rounded-2xl p-4.5 text-sm leading-relaxed shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white rounded-br-none'
                      : 'bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-bl-none shadow-md'
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Retrieval Citations */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800/80 space-y-2">
                      <div className="text-[11px] font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider flex items-center space-x-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Verified Citations ({msg.citations.length})</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {msg.citations.map((c, citIdx) => (
                          <button
                            key={citIdx}
                            onClick={() => setSelectedCitation(c)}
                            className="bg-slate-50 dark:bg-slate-950 hover:bg-indigo-50 dark:hover:bg-indigo-950/80 border border-slate-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-700/60 text-slate-700 dark:text-slate-300 text-xs px-2.5 py-1 rounded-lg flex items-center space-x-1.5 transition-all text-left"
                          >
                            <span className="w-4 h-4 rounded-full bg-indigo-100 dark:bg-indigo-900/80 text-indigo-700 dark:text-indigo-300 text-[10px] flex items-center justify-center font-bold">
                              {citIdx + 1}
                            </span>
                            <span className="font-medium truncate max-w-[140px]">{c.title}</span>
                            {c.page_number && <span className="text-[10px] text-slate-400 dark:text-slate-500">p.{c.page_number}</span>}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Metadata telemetry badge */}
                  {msg.metadata && (
                    <div className="mt-3 pt-2 text-[10px] text-slate-400 dark:text-slate-500 flex items-center space-x-3">
                      {msg.metadata.retrieval_latency_ms && (
                        <span className="flex items-center space-x-1">
                          <Clock className="w-2.5 h-2.5" />
                          <span>{Math.round(msg.metadata.retrieval_latency_ms)}ms latency</span>
                        </span>
                      )}
                      {msg.metadata.chunks_retrieved && (
                        <span className="flex items-center space-x-1">
                          <Layers className="w-2.5 h-2.5" />
                          <span>{msg.metadata.chunks_retrieved} chunks retrieved</span>
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
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-bl-none p-4 text-xs text-slate-600 dark:text-slate-400 flex items-center space-x-3 shadow-md">
                <Cpu className="w-4 h-4 text-indigo-600 dark:text-indigo-400 animate-spin" />
                <span>Retrieving knowledge, reranking candidates, and formulating answer...</span>
              </div>
            </div>
          )}

          {error && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur">
          <form onSubmit={handleSendMessage} className="flex items-center space-x-3 max-w-4xl mx-auto">
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder="Ask anything grounded against your ingested documents..."
              disabled={isSending}
              className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600 focus:border-indigo-500 rounded-xl px-4 py-3 text-sm text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none transition-colors shadow-sm"
            />
            <button
              type="submit"
              disabled={isSending || !inputQuestion.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white p-3 rounded-xl transition-all shadow-md shadow-indigo-600/20 disabled:opacity-40"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* Citation Inspector Modal */}
      {selectedCitation && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-2xl p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-4">
              <div>
                <h3 className="font-bold text-slate-900 dark:text-white text-base truncate max-w-md">
                  Citation: {selectedCitation.title}
                </h3>
                <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {selectedCitation.page_number && <span>Page: {selectedCitation.page_number}</span>}
                  {selectedCitation.chunk_index !== undefined && <span>Chunk Index: #{selectedCitation.chunk_index}</span>}
                  {selectedCitation.similarity_score !== undefined && (
                    <span>Score: {(selectedCitation.similarity_score * 100).toFixed(1)}%</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setSelectedCitation(null)}
                className="text-slate-400 hover:text-slate-900 dark:hover:text-white text-sm p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-600 dark:text-slate-400">Extracted Source Snippet</label>
              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4 rounded-xl text-xs font-mono text-slate-800 dark:text-slate-300 leading-relaxed max-h-80 overflow-y-auto">
                {selectedCitation.snippet || 'No raw snippet preview preserved.'}
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                onClick={() => setSelectedCitation(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-semibold text-slate-700 dark:text-white rounded-xl transition-colors"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default RAGChatView;
