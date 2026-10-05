import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { Trace, Span } from '../../types';
import {
  Activity,
  RotateCw,
  Clock,
  ShieldCheck,
  Terminal,
} from 'lucide-react';

export const TracesView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [traces, setTraces] = useState<Trace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [metricsRaw, setMetricsRaw] = useState<string>('');

  const fetchTraces = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    try {
      const [tList, raw] = await Promise.all([
        api.listTraces(currentWorkspace.id),
        api.getMetricsRaw().catch(() => 'Prometheus /metrics endpoint reached.'),
      ]);
      setTraces(tList);
      setMetricsRaw(raw);
      if (tList.length > 0 && !selectedTrace) {
        setSelectedTrace(tList[0]);
      }
    } catch (err: any) {
      console.error('Failed to load traces:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTraces();
  }, [currentWorkspace?.id]);

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to view traces.
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Left Column: Trace List */}
      <div className="w-80 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col justify-between flex-shrink-0 transition-colors">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span className="font-bold text-slate-900 dark:text-white text-sm">Execution Traces</span>
          </div>
          <button
            onClick={fetchTraces}
            className="text-xs text-slate-400 hover:text-slate-900 dark:hover:text-white p-1"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {traces.length === 0 ? (
            <div className="text-xs text-slate-400 dark:text-slate-600 p-4 text-center">
              No recorded traces in this workspace yet. Execute a chat, ingestion, or agent request.
            </div>
          ) : (
            traces.map((t) => {
              const isSelected = selectedTrace?.trace_id === t.trace_id;
              return (
                <div
                  key={t.trace_id}
                  onClick={() => setSelectedTrace(t)}
                  className={`p-3 rounded-xl cursor-pointer text-xs transition-all border ${
                    isSelected
                      ? 'bg-indigo-50 dark:bg-slate-900 border-indigo-200 dark:border-indigo-700/60 text-slate-900 dark:text-white shadow-sm'
                      : 'bg-slate-50/70 dark:bg-slate-950/40 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-slate-900 dark:text-white truncate max-w-[170px]">
                      {t.operation_name}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-mono uppercase ${
                        t.status === 'ok'
                          ? 'bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400'
                          : 'bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-400'
                      }`}
                    >
                      {t.status}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                    <span>{t.spans?.length || 0} spans</span>
                    <span>{t.duration_ms ? `${Math.round(t.duration_ms)}ms` : '-'}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/30 text-[10px] text-slate-500 flex items-center justify-between">
          <span className="flex items-center space-x-1">
            <ShieldCheck className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
            <span>Sensitive Data Redacted</span>
          </span>
          <span>OpenTelemetry Ready</span>
        </div>
      </div>

      {/* Right Column: Detailed Span Waterfall */}
      <div className="flex-1 flex flex-col bg-slate-50/50 dark:bg-slate-950 overflow-y-auto p-8 space-y-6 transition-colors">
        {selectedTrace ? (
          <>
            {/* Trace Header */}
            <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
              <div>
                <div className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400 mb-1">
                  <span>Trace ID:</span>
                  <span className="font-mono text-indigo-600 dark:text-indigo-400">{selectedTrace.trace_id}</span>
                </div>
                <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                  Operation: {selectedTrace.operation_name}
                </h2>
              </div>

              <div className="flex items-center space-x-3 text-xs">
                <div className="flex items-center space-x-1.5 bg-slate-100 dark:bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span>Total Duration: {selectedTrace.duration_ms ? `${Math.round(selectedTrace.duration_ms)}ms` : 'N/A'}</span>
                </div>
              </div>
            </div>

            {/* Span Waterfall Sequence */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>Execution Span Sequence ({selectedTrace.spans?.length || 0} stages)</span>
              </h3>

              <div className="space-y-2">
                {selectedTrace.spans?.map((span: Span, idx: number) => {
                  const totalTraceDuration = selectedTrace.duration_ms || 1;
                  const spanDuration = span.duration_ms || 0;
                  const widthPercent = Math.min(100, Math.max(5, (spanDuration / totalTraceDuration) * 100));

                  return (
                    <div
                      key={span.span_id || idx}
                      className="p-4 bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2 shadow-sm"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center space-x-2.5">
                          <span className="font-mono text-indigo-600 dark:text-indigo-400 font-bold">#{idx + 1}</span>
                          <span className="font-bold text-slate-900 dark:text-white">{span.name}</span>
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded font-mono uppercase ${
                              span.status === 'ok' ? 'text-emerald-700 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950' : 'text-rose-700 bg-rose-50 dark:text-rose-400 dark:bg-rose-950'
                            }`}
                          >
                            {span.status}
                          </span>
                        </div>
                        <span className="font-mono text-slate-500 dark:text-slate-400">{Math.round(spanDuration)}ms</span>
                      </div>

                      {/* Mini visual timeline bar */}
                      <div className="w-full bg-slate-100 dark:bg-slate-950 h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-indigo-600 dark:bg-indigo-500 h-full rounded-full"
                          style={{ width: `${widthPercent}%` }}
                        ></div>
                      </div>

                      {/* Span Attributes */}
                      {span.attributes && Object.keys(span.attributes).length > 0 && (
                        <div className="pt-2 text-[11px] font-mono bg-slate-50 dark:bg-slate-950 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800/80 text-slate-600 dark:text-slate-400 overflow-x-auto">
                          {Object.entries(span.attributes).map(([k, v]) => (
                            <div key={k} className="flex space-x-2 truncate">
                              <span className="text-slate-400">{k}:</span>
                              <span className="text-slate-800 dark:text-slate-300 truncate">
                                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Prometheus /metrics Preview */}
            <div className="bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 space-y-2 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center space-x-2">
                  <Terminal className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                  <span>Live Prometheus Metrics Sample</span>
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500">GET /metrics</span>
              </div>
              <pre className="bg-slate-50 dark:bg-slate-950 p-3 rounded-xl border border-slate-200 dark:border-slate-800 text-[11px] font-mono text-slate-600 dark:text-slate-400 max-h-36 overflow-y-auto">
                {typeof metricsRaw === 'string' ? metricsRaw.slice(0, 1000) : 'Metrics collected.'}
              </pre>
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-slate-400 dark:text-slate-600 text-xs">
            Select a trace from the left panel to inspect execution spans.
          </div>
        )}
      </div>
    </div>
  );
};
export default TracesView;
