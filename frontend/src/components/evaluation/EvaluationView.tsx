import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { EvaluationRun, EvaluationDataset, ExperimentComparison } from '../../types';
import {
  FlaskConical,
  Play,
  RotateCw,
  GitCompare,
  TrendingUp,
  TrendingDown,
  Sparkles,
} from 'lucide-react';

export const EvaluationView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [loading, setLoading] = useState(true);

  // Run Benchmark Form
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [retrievalMode, setRetrievalMode] = useState<'semantic' | 'hybrid' | 'reranked'>('hybrid');
  const [topK, setTopK] = useState<number>(5);
  const [evaluatorType, setEvaluatorType] = useState<'deterministic' | 'llm'>('deterministic');
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);

  // Experiment Comparison State
  const [baselineRunId, setBaselineRunId] = useState<string>('');
  const [candidateRunId, setCandidateRunId] = useState<string>('');
  const [comparison, setComparison] = useState<ExperimentComparison | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);

  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchData = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const [runsData, datasetsData] = await Promise.all([
        api.listEvaluationRuns(currentWorkspace.id),
        api.listEvaluationDatasets(currentWorkspace.id),
      ]);
      setRuns(runsData);
      setDatasets(datasetsData);
      if (datasetsData.length > 0 && !selectedDatasetId) {
        setSelectedDatasetId(datasetsData[0].id);
      }
      if (runsData.length >= 2 && !baselineRunId && !candidateRunId) {
        setBaselineRunId(runsData[1].run_id);
        setCandidateRunId(runsData[0].run_id);
      }
    } catch (err: any) {
      console.error('Failed to load evaluation data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [currentWorkspace?.id]);

  const handleLaunchEvaluation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !selectedDatasetId) return;

    setIsEvaluating(true);
    setMessage(null);

    try {
      const run = await api.runEvaluation(currentWorkspace.id, selectedDatasetId, {
        retrieval_mode: retrievalMode,
        top_k: topK,
        evaluator_type: evaluatorType,
      });

      setMessage({ text: `Evaluation run completed! Recall@5: ${((run.mean_recall_at_k ?? 0) * 100).toFixed(1)}%`, type: 'success' });
      await fetchData();
    } catch (err: any) {
      setMessage({ text: `Evaluation failed: ${err.message}`, type: 'error' });
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleCompare = async () => {
    if (!currentWorkspace || !baselineRunId || !candidateRunId) return;
    setIsComparing(true);
    try {
      const comp = await api.compareExperiments(currentWorkspace.id, baselineRunId, candidateRunId);
      setComparison(comp);
    } catch (err: any) {
      setMessage({ text: `Comparison failed: ${err.message}`, type: 'error' });
    } finally {
      setIsComparing(false);
    }
  };

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to access the Evaluation Lab.
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight flex items-center space-x-3">
            <FlaskConical className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
            <span>Evaluation & Benchmark Lab</span>
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Deterministic Recall@K, MRR, nDCG, and Citation F1 metrics with automated experiment comparisons.
          </p>
        </div>

        <button
          onClick={fetchData}
          disabled={loading}
          className="self-start md:self-auto flex items-center space-x-2 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700/80 px-4 py-2 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-300 transition-all shadow-sm disabled:opacity-50"
        >
          <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Results</span>
        </button>
      </div>

      {message && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-center justify-between ${
            message.type === 'success'
              ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
              : 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300'
          }`}
        >
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)} className="text-xs hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Launch Benchmark Controls */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900 dark:text-white mb-4 flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <span>Run Evaluation Experiment</span>
        </h2>

        <form onSubmit={handleLaunchEvaluation} className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div>
            <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">Target Evaluation Dataset</label>
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.example_count} queries)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">Retrieval Architecture</label>
            <select
              value={retrievalMode}
              onChange={(e) => setRetrievalMode(e.target.value as any)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
            >
              <option value="semantic">Baseline Semantic Dense Retrieval</option>
              <option value="hybrid">Improved Hybrid (Dense + Sparse BM25)</option>
              <option value="reranked">Reranked (Hybrid + Cross-Encoder)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">Answer Evaluator</label>
            <select
              value={evaluatorType}
              onChange={(e) => setEvaluatorType(e.target.value as any)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
            >
              <option value="deterministic">Deterministic Ground Truth (Isolated)</option>
              <option value="llm">LLM-Assisted Judge (Explicitly Labelled)</option>
            </select>
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isEvaluating || !selectedDatasetId}
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all shadow-md shadow-indigo-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isEvaluating ? 'Running Experiment...' : 'Execute Evaluation'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Comparison Engine */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center space-x-2">
            <GitCompare className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
            <span>Experiment A/B Comparison</span>
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs mb-4">
          <div>
            <label className="block text-slate-600 dark:text-slate-400 mb-1">Baseline Run (Experiment A)</label>
            <select
              value={baselineRunId}
              onChange={(e) => setBaselineRunId(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
            >
              {runs.map((r) => {
                const runIdShort = (r.run_id || '').slice(0, 8);
                const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '';
                return (
                  <option key={r.run_id} value={r.run_id}>
                    {(r.config?.retrieval_mode || 'hybrid').toUpperCase()} ({runIdShort}) {timeStr ? `- ${timeStr}` : ''}
                  </option>
                );
              })}
            </select>
          </div>

          <div>
            <label className="block text-slate-600 dark:text-slate-400 mb-1">Candidate Run (Experiment B)</label>
            <select
              value={candidateRunId}
              onChange={(e) => setCandidateRunId(e.target.value)}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
            >
              {runs.map((r) => {
                const runIdShort = (r.run_id || '').slice(0, 8);
                const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '';
                return (
                  <option key={r.run_id} value={r.run_id}>
                    {(r.config?.retrieval_mode || 'hybrid').toUpperCase()} ({runIdShort}) {timeStr ? `- ${timeStr}` : ''}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="flex items-end">
            <button
              onClick={handleCompare}
              disabled={isComparing || !baselineRunId || !candidateRunId}
              className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all shadow-md shadow-cyan-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <GitCompare className="w-3.5 h-3.5" />
              <span>{isComparing ? 'Comparing...' : 'Compare Experiments'}</span>
            </button>
          </div>
        </div>

        {/* Diff Result Grid */}
        {comparison && (
          <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl space-y-4">
            <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">Metrics Differential</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              {Object.entries(comparison.metrics_diff).map(([metricKey, diffVal]) => (
                <div key={metricKey} className="p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl space-y-1 shadow-sm">
                  <span className="text-slate-500 dark:text-slate-400 font-medium capitalize">{metricKey.replace('diff_', '').replace(/_/g, ' ')}</span>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-900 dark:text-white text-base">
                      {typeof diffVal === 'number' ? diffVal.toFixed(3) : String(diffVal)}
                    </span>
                    {typeof diffVal === 'number' && (
                      <span
                        className={`flex items-center space-x-0.5 text-xs font-semibold ${
                          diffVal >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                        }`}
                      >
                        {diffVal >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        <span>{diffVal.toFixed(3)}</span>
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Historical Runs Table */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-900 dark:text-white text-base">Evaluation Run History</span>
            <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded-full">
              {runs.length} runs
            </span>
          </div>
        </div>

        {runs.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs">
            No evaluation runs recorded. Run an experiment above to benchmark your RAG pipeline.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-xs uppercase font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-3.5">Run ID & Mode</th>
                  <th className="px-6 py-3.5">Recall@5</th>
                  <th className="px-6 py-3.5">MRR</th>
                  <th className="px-6 py-3.5">nDCG@5</th>
                  <th className="px-6 py-3.5">Citation F1</th>
                  <th className="px-6 py-3.5">Latency</th>
                  <th className="px-6 py-3.5">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/60 text-xs">
                {runs.map((r) => (
                  <tr key={r.run_id} className="hover:bg-slate-50 dark:hover:bg-slate-850/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-slate-900 dark:text-white font-mono uppercase">{r.config?.retrieval_mode || 'hybrid'}</div>
                      <div className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">{r.run_id}</div>
                    </td>

                    <td className="px-6 py-4 font-mono font-semibold text-slate-900 dark:text-white">
                      {((r.mean_recall_at_k ?? 0) * 100).toFixed(1)}%
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-700 dark:text-slate-200">
                      {(r.mean_mrr ?? 0).toFixed(3)}
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-700 dark:text-slate-200">
                      {(r.mean_ndcg_at_k ?? 0).toFixed(3)}
                    </td>

                    <td className="px-6 py-4 font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                      {((r.mean_citation_f1 ?? 0) * 100).toFixed(1)}%
                    </td>

                    <td className="px-6 py-4 font-mono text-slate-600 dark:text-slate-400">
                      {Math.round(r.mean_latency_ms)}ms
                    </td>

                    <td className="px-6 py-4 text-slate-500">
                      {new Date(r.timestamp).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
export default EvaluationView;
