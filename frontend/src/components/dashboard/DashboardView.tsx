import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { Source, Conversation, AgentExecution, EvaluationRun } from '../../types';
import {
  FileText,
  MessageSquare,
  Bot,
  FlaskConical,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  RefreshCw,
  Sparkles,
} from 'lucide-react';

export const DashboardView: React.FC = () => {
  const navigate = useNavigate();
  const { currentWorkspace } = useAuth();
  const [sources, setSources] = useState<Source[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentExecution[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvaluationRun[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDashboardData = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const [srcRes, convRes, agentRes, evalRes] = await Promise.allSettled([
        api.listSources(currentWorkspace.id),
        api.listConversations(currentWorkspace.id),
        api.listAgentExecutions(currentWorkspace.id),
        api.listEvaluationRuns(currentWorkspace.id),
      ]);

      if (srcRes.status === 'fulfilled') setSources(srcRes.value);
      if (convRes.status === 'fulfilled') setConversations(convRes.value);
      if (agentRes.status === 'fulfilled') setAgentRuns(agentRes.value);
      if (evalRes.status === 'fulfilled') setEvalRuns(evalRes.value);
    } catch (err) {
      console.error('Error fetching dashboard metrics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, [currentWorkspace?.id]);

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Please select or create a workspace to view the dashboard.
      </div>
    );
  }

  const completedSources = sources.filter((s) => s.status === 'completed').length;
  const pendingSources = sources.filter((s) => s.status === 'pending' || s.status === 'processing').length;
  const failedSources = sources.filter((s) => s.status === 'failed').length;

  const latestEval = evalRuns.length > 0 ? evalRuns[0] : null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center space-x-2 text-indigo-600 dark:text-indigo-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Workspace Operations Hub</span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {currentWorkspace.name}
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            System overview of indexed knowledge, neural chat threads, agent tools & deterministic benchmarks.
          </p>
        </div>

        <button
          onClick={loadDashboardData}
          disabled={loading}
          className="self-start md:self-auto flex items-center space-x-2 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700/80 px-4 py-2 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-300 transition-all shadow-sm disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Knowledge Sources */}
        <div
          onClick={() => navigate('/knowledge')}
          className="bg-white dark:bg-slate-900/60 hover:shadow-md dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 p-5 rounded-2xl transition-all cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Indexed Sources</span>
            <div className="p-2 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 rounded-xl group-hover:scale-110 transition-transform">
              <FileText className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900 dark:text-white mb-2">{sources.length}</div>
          <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-slate-400">
            <span className="flex items-center space-x-1 text-emerald-600 dark:text-emerald-400 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{completedSources} active</span>
            </span>
            {failedSources > 0 && (
              <span className="flex items-center space-x-1 text-rose-600 dark:text-rose-400 font-medium">
                <AlertCircle className="w-3.5 h-3.5" />
                <span>{failedSources} failed</span>
              </span>
            )}
          </div>
        </div>

        {/* Conversations */}
        <div
          onClick={() => navigate('/chat')}
          className="bg-white dark:bg-slate-900/60 hover:shadow-md dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 p-5 rounded-2xl transition-all cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Active RAG Chats</span>
            <div className="p-2 bg-cyan-50 dark:bg-cyan-950/60 text-cyan-600 dark:text-cyan-400 rounded-xl group-hover:scale-110 transition-transform">
              <MessageSquare className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900 dark:text-white mb-2">{conversations.length}</div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Multi-turn grounded query sessions</p>
        </div>

        {/* Agent Executions */}
        <div
          onClick={() => navigate('/agent')}
          className="bg-white dark:bg-slate-900/60 hover:shadow-md dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 p-5 rounded-2xl transition-all cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Agent Runs</span>
            <div className="p-2 bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 rounded-xl group-hover:scale-110 transition-transform">
              <Bot className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900 dark:text-white mb-2">{agentRuns.length}</div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Autonomous tool orchestration executions</p>
        </div>

        {/* Evaluation Runs */}
        <div
          onClick={() => navigate('/evaluation')}
          className="bg-white dark:bg-slate-900/60 hover:shadow-md dark:hover:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 p-5 rounded-2xl transition-all cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Evaluation Runs</span>
            <div className="p-2 bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-xl group-hover:scale-110 transition-transform">
              <FlaskConical className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900 dark:text-white mb-2">{evalRuns.length}</div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Retrieval & groundedness experiments</p>
        </div>
      </div>

      {/* Main Grid: Ingestion Status & Evaluation Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Ingestion & Knowledge Status */}
        <div className="bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Ingestion Pipeline Status</h2>
              <button
                onClick={() => navigate('/knowledge')}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center space-x-1 font-medium"
              >
                <span>Manage</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-xl">
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-slate-500 dark:text-slate-400">Indexing Completeness</span>
                  <span className="text-indigo-600 dark:text-indigo-400 font-semibold">
                    {sources.length > 0
                      ? `${Math.round((completedSources / sources.length) * 100)}%`
                      : '0%'}
                  </span>
                </div>
                <div className="w-full bg-slate-200 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-indigo-600 dark:bg-indigo-500 h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${sources.length > 0 ? (completedSources / sources.length) * 100 : 0}%`,
                    }}
                  ></div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-xl">
                  <div className="text-xs text-slate-500 dark:text-slate-400">Completed</div>
                  <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-1">{completedSources}</div>
                </div>
                <div className="p-2.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-xl">
                  <div className="text-xs text-slate-500 dark:text-slate-400">Queued</div>
                  <div className="text-lg font-bold text-amber-600 dark:text-amber-400 mt-1">{pendingSources}</div>
                </div>
                <div className="p-2.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-xl">
                  <div className="text-xs text-slate-500 dark:text-slate-400">Errors</div>
                  <div className="text-lg font-bold text-rose-600 dark:text-rose-400 mt-1">{failedSources}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-200 dark:border-slate-800/80 text-xs text-slate-500 dark:text-slate-400 flex items-center justify-between">
            <span>Storage: Supabase Storage</span>
            <span>Vector: Qdrant Cloud</span>
          </div>
        </div>

        {/* Evaluation Summary Card */}
        <div className="bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 lg:col-span-2 flex flex-col justify-between shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white">Latest Evaluation Benchmark</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Groundedness, Recall@K and MRR metrics computed against ground truth
                </p>
              </div>
              <button
                onClick={() => navigate('/evaluation')}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 flex items-center space-x-1 font-medium"
              >
                <span>View All Runs</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            {latestEval ? (
              <div className="space-y-4">
                <div className="flex items-center space-x-3 text-xs bg-slate-50 dark:bg-slate-950 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                  <span className="font-semibold text-slate-900 dark:text-white">Mode:</span>
                  <span className="px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 font-mono text-[11px] uppercase">
                    {latestEval.config?.retrieval_mode || 'hybrid'}
                  </span>
                  <span className="text-slate-400 dark:text-slate-500">•</span>
                  <span className="text-slate-600 dark:text-slate-400">Total Examples: {latestEval.total_examples}</span>
                  <span className="text-slate-400 dark:text-slate-500">•</span>
                  <span className="text-slate-600 dark:text-slate-400">Avg Latency: {Math.round(latestEval.mean_latency_ms)}ms</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl">
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Recall@5</div>
                    <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                      {((latestEval.mean_recall_at_k ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl">
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">MRR</div>
                    <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                      {(latestEval.mean_mrr ?? 0).toFixed(3)}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl">
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">nDCG@5</div>
                    <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                      {(latestEval.mean_ndcg_at_k ?? 0).toFixed(3)}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl">
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Citation F1</div>
                    <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                      {((latestEval.mean_citation_f1 ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800/80 rounded-xl p-8 text-center text-slate-500 dark:text-slate-400">
                <FlaskConical className="w-8 h-8 mx-auto text-slate-400 dark:text-slate-600 mb-2" />
                <p className="text-sm">No evaluation runs recorded in this workspace yet.</p>
                <button
                  onClick={() => navigate('/evaluation')}
                  className="mt-3 inline-flex items-center space-x-1.5 text-xs text-indigo-600 dark:text-indigo-400 font-semibold hover:underline"
                >
                  <span>Launch retrieval benchmark</span>
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800/80 text-xs text-slate-500 dark:text-slate-400">
            Automated regression defense: compare baseline semantic vs hybrid & cross-encoder reranking.
          </div>
        </div>
      </div>

      {/* Lower Row: Recent Chats & Recent Agent Runs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Chats */}
        <div className="bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-slate-900 dark:text-white">Recent RAG Conversations</h2>
            <button
              onClick={() => navigate('/chat')}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-medium flex items-center space-x-1"
            >
              <span>View all</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {conversations.length === 0 ? (
            <div className="text-xs text-slate-500 py-6 text-center">
              No conversations yet. Start a new RAG question in the chat view.
            </div>
          ) : (
            <div className="space-y-2">
              {conversations.slice(0, 4).map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate('/chat')}
                  className="p-3 bg-slate-50 dark:bg-slate-950/70 hover:bg-slate-100 dark:hover:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl cursor-pointer transition-colors flex items-center justify-between"
                >
                  <div className="flex items-center space-x-3">
                    <MessageSquare className="w-4 h-4 text-cyan-600 dark:text-cyan-400 flex-shrink-0" />
                    <div>
                      <div className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate max-w-xs sm:max-w-md">
                        {c.title}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {new Date(c.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400 dark:text-slate-600" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Agent Executions */}
        <div className="bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-slate-900 dark:text-white">Recent Agent Executions</h2>
            <button
              onClick={() => navigate('/agent')}
              className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-medium flex items-center space-x-1"
            >
              <span>View all</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {agentRuns.length === 0 ? (
            <div className="text-xs text-slate-500 py-6 text-center">
              No agent runs logged yet. Execute autonomous multi-tool tasks in Agent Studio.
            </div>
          ) : (
            <div className="space-y-2">
              {agentRuns.slice(0, 4).map((run) => {
                const responseText = run.query || run.final_response || 'Autonomous Agent Task';
                const displayText = responseText.length > 60 ? `${responseText.slice(0, 60)}...` : responseText;
                const stepsCount = run.steps_count ?? run.steps?.length ?? run.trace?.length ?? 0;
                const duration = Math.round(run.total_latency_ms ?? run.total_duration_ms ?? 0);
                return (
                  <div
                    key={run.execution_id}
                    onClick={() => navigate('/agent')}
                    className="p-3 bg-slate-50 dark:bg-slate-950/70 hover:bg-slate-100 dark:hover:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl cursor-pointer transition-colors flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-3 truncate">
                      <Bot className="w-4 h-4 text-purple-600 dark:text-purple-400 flex-shrink-0" />
                      <div className="truncate">
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">
                          {displayText}
                        </div>
                        <div className="flex items-center space-x-2 text-[11px] text-slate-500">
                          <span>{stepsCount} tool steps</span>
                          <span>•</span>
                          <span className="flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>{duration}ms</span>
                          </span>
                        </div>
                      </div>
                    </div>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-medium uppercase ${
                        run.status === 'completed'
                          ? 'bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                          : 'bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default DashboardView;
