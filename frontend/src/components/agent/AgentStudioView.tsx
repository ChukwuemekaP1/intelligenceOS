import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { AgentExecution, ToolExecutionStep } from '../../types';
import {
  Bot,
  Play,
  Clock,
  CheckCircle2,
  Database,
  Calculator,
  Search,
  Code,
  ShieldCheck,
  RotateCw,
} from 'lucide-react';

export const AgentStudioView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [prompt, setPrompt] = useState('');
  const [maxSteps, setMaxSteps] = useState(6);
  const [selectedTools, setSelectedTools] = useState<string[]>([
    'knowledge_search',
    'read_only_sql',
    'calculator',
    'web_search',
  ]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentExecution, setCurrentExecution] = useState<AgentExecution | null>(null);
  const [history, setHistory] = useState<AgentExecution[]>([]);
  const [error, setError] = useState<string | null>(null);

  const availableTools = [
    {
      name: 'knowledge_search',
      label: 'Knowledge Search',
      desc: 'Retrieves grounded context from workspace documents',
      icon: Database,
    },
    {
      name: 'read_only_sql',
      label: 'Read-Only SQL',
      desc: 'Safely queries relational data with AST mutation defense',
      icon: Code,
    },
    {
      name: 'calculator',
      label: 'Safe Calculator',
      desc: 'Evaluates verified arithmetic equations',
      icon: Calculator,
    },
    {
      name: 'web_search',
      label: 'Web Search',
      desc: 'Queries external real-time facts with SSRF filtering',
      icon: Search,
    },
  ];

  const fetchHistory = async () => {
    if (!currentWorkspace) return;
    try {
      const runs = await api.listAgentExecutions(currentWorkspace.id);
      setHistory(runs);
      if (runs.length > 0 && !currentExecution) {
        handleSelectRun(runs[0]);
      }
    } catch (err: any) {
      console.error('Failed to load agent history:', err);
    }
  };

  const handleSelectRun = async (run: AgentExecution) => {
    if (!currentWorkspace) return;
    // Set immediate summary data
    setCurrentExecution(run);
    // Fetch full execution trace if needed
    try {
      const full = await api.getAgentExecution(currentWorkspace.id, run.execution_id);
      if (full) {
        setCurrentExecution(full);
      }
    } catch (err) {
      console.warn('Could not load detailed trace for agent run:', err);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [currentWorkspace?.id]);

  const toggleTool = (toolName: string) => {
    if (selectedTools.includes(toolName)) {
      if (selectedTools.length > 1) {
        setSelectedTools(selectedTools.filter((t) => t !== toolName));
      }
    } else {
      setSelectedTools([...selectedTools, toolName]);
    }
  };

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !prompt.trim() || isExecuting) return;

    setIsExecuting(true);
    setError(null);

    try {
      const exec = await api.executeAgent(currentWorkspace.id, prompt.trim(), {
        allowed_tools: selectedTools,
        max_steps: maxSteps,
      });

      setCurrentExecution(exec);
      setHistory([exec, ...history]);
    } catch (err: any) {
      setError(err.message || 'Agent execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to enter Agent Studio.
      </div>
    );
  }

  const stepsList = currentExecution?.trace || currentExecution?.steps || [];
  const totalDuration = Math.round(
    currentExecution?.total_latency_ms ?? currentExecution?.total_duration_ms ?? 0
  );

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Left Column: Form & History */}
      <div className="w-96 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex flex-col justify-between flex-shrink-0 overflow-y-auto transition-colors">
        <div className="p-6 space-y-6">
          <div>
            <div className="flex items-center space-x-2 text-purple-600 dark:text-purple-400 text-xs font-semibold uppercase tracking-wider mb-1">
              <Bot className="w-4 h-4" />
              <span>Autonomous Task Orchestration</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">Agent Studio</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Multi-tool ReAct loop executing step-by-step actions with budget controls.
            </p>
          </div>

          <form onSubmit={handleExecute} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Agent Objective / Prompt
              </label>
              <textarea
                rows={4}
                required
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. Find revenue metrics in the Q3 report, calculate the 18% tax margin using calculator, and summarize findings."
                className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl p-3 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-purple-500 placeholder-slate-400 dark:placeholder-slate-500 leading-relaxed resize-none shadow-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
                Allowed Tools Sandbox ({selectedTools.length} enabled)
              </label>
              <div className="space-y-2">
                {availableTools.map((t) => {
                  const Icon = t.icon;
                  const isChecked = selectedTools.includes(t.name);
                  return (
                    <div
                      key={t.name}
                      onClick={() => toggleTool(t.name)}
                      className={`p-2.5 rounded-xl border text-xs cursor-pointer flex items-center justify-between transition-colors ${
                        isChecked
                          ? 'bg-purple-50 dark:bg-purple-950/30 border-purple-200 dark:border-purple-800/60 text-purple-900 dark:text-purple-200 shadow-sm'
                          : 'bg-white dark:bg-slate-900/60 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center space-x-2.5 truncate">
                        <Icon className={`w-3.5 h-3.5 ${isChecked ? 'text-purple-600 dark:text-purple-400' : 'text-slate-400 dark:text-slate-500'}`} />
                        <div>
                          <div className="font-semibold text-slate-900 dark:text-white">{t.label}</div>
                          <div className="text-[10px] text-slate-500 truncate max-w-[200px]">{t.desc}</div>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        readOnly
                        className="accent-purple-600 rounded"
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1 font-semibold text-slate-700 dark:text-slate-300">
                <span>Max Step Budget</span>
                <span className="font-mono text-purple-600 dark:text-purple-400">{maxSteps} steps</span>
              </div>
              <input
                type="range"
                min="2"
                max="10"
                value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value))}
                className="w-full accent-purple-600"
              />
            </div>

            <button
              type="submit"
              disabled={isExecuting || !prompt.trim()}
              className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold py-3 rounded-xl text-xs transition-all shadow-md shadow-purple-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isExecuting ? 'Agent Reasoning & Executing...' : 'Launch Agent Execution'}</span>
            </button>
          </form>

          {error && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300">
              {error}
            </div>
          )}
        </div>

        {/* Prior Executions */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/30">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
            <span>Execution Log</span>
            <button onClick={fetchHistory} className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-300">
              <RotateCw className="w-3 h-3" />
            </button>
          </div>
          <div className="max-h-40 overflow-y-auto space-y-1.5">
            {history.length === 0 ? (
              <div className="text-xs text-slate-400 dark:text-slate-600">No past runs in log.</div>
            ) : (
              history.map((run) => {
                const title = run.query || run.final_response || 'Agent Run';
                const displayTitle = title.length > 35 ? `${title.slice(0, 35)}...` : title;
                const stepsCount = run.steps_count ?? run.steps?.length ?? run.trace?.length ?? 0;
                return (
                  <div
                    key={run.execution_id}
                    onClick={() => handleSelectRun(run)}
                    className={`p-2 rounded-xl text-xs cursor-pointer flex items-center justify-between transition-colors ${
                      currentExecution?.execution_id === run.execution_id
                        ? 'bg-purple-50 dark:bg-purple-950/50 border border-purple-200 dark:border-purple-800/60 text-purple-900 dark:text-purple-200 font-medium'
                        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-900'
                    }`}
                  >
                    <div className="truncate max-w-[190px]">
                      {displayTitle}
                    </div>
                    <span className="text-[10px] text-slate-400 dark:text-slate-500">{stepsCount} steps</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Right Column: Execution Trace & Final Output */}
      <div className="flex-1 flex flex-col bg-slate-50/50 dark:bg-slate-950 overflow-y-auto p-8 space-y-6 transition-colors">
        {currentExecution ? (
          <>
            {/* Header Status */}
            <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm">
              <div>
                <div className="flex items-center space-x-2 mb-1">
                  <span className="text-xs text-slate-500 dark:text-slate-400">Execution ID:</span>
                  <span className="text-xs font-mono text-purple-600 dark:text-purple-400">
                    {currentExecution.execution_id}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Safe Tool Orchestration Trace</h3>
              </div>

              <div className="flex items-center space-x-3 text-xs">
                <div className="flex items-center space-x-1.5 text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span>{totalDuration}ms Total</span>
                </div>
                <div
                  className={`px-3 py-1.5 rounded-xl font-semibold uppercase text-xs flex items-center space-x-1.5 ${
                    currentExecution.status === 'completed'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                      : 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{currentExecution.status}</span>
                </div>
              </div>
            </div>

            {/* Sequence Timeline of Tool Steps */}
            <div className="space-y-4">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>Sanitized Execution Steps ({stepsList.length})</span>
              </h4>

              {stepsList.length === 0 ? (
                <div className="p-4 bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-500 dark:text-slate-400 shadow-sm">
                  {currentExecution.query
                    ? `Task: "${currentExecution.query}" - no intermediate tool trace needed.`
                    : 'No intermediate tools were called; agent solved request directly.'}
                </div>
              ) : (
                <div className="space-y-3">
                  {stepsList.map((step: ToolExecutionStep, idx: number) => {
                    const stepNum = step.step_index ?? step.step_number ?? idx + 1;
                    const toolName = step.tool_name || step.action || 'tool_step';
                    const stepInputs = step.inputs ?? step.tool_input ?? {};
                    const stepOutputs = step.outputs ?? step.tool_result ?? {};
                    const isSuccess = step.status === 'success' || (!step.error && step.status !== 'error');

                    return (
                      <div
                        key={stepNum}
                        className="p-5 bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl space-y-3 shadow-sm"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <span className="w-6 h-6 rounded-full bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800 text-xs font-bold flex items-center justify-center font-mono">
                              {stepNum}
                            </span>
                            <span className="text-sm font-bold text-slate-900 dark:text-white font-mono">
                              {toolName}
                            </span>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded uppercase font-semibold ${
                                isSuccess
                                  ? 'bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                                  : 'bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                              }`}
                            >
                              {isSuccess ? 'success' : 'error'}
                            </span>
                          </div>
                          {step.duration_ms !== undefined && (
                            <span className="text-xs text-slate-400 dark:text-slate-500 font-mono">
                              {Math.round(step.duration_ms)}ms
                            </span>
                          )}
                        </div>

                        {step.thought && (
                          <p className="text-xs text-slate-600 dark:text-slate-400 italic">
                            {step.thought}
                          </p>
                        )}

                        {/* Inputs and Outputs - safe & sanitized */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                          <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800/80">
                            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                              Safe Inputs
                            </div>
                            <pre className="text-slate-800 dark:text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
                              {typeof stepInputs === 'object' ? JSON.stringify(stepInputs, null, 2) : String(stepInputs)}
                            </pre>
                          </div>

                          <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800/80">
                            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1">
                              Step Result
                            </div>
                            <pre className="text-slate-800 dark:text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
                              {typeof stepOutputs === 'object' ? JSON.stringify(stepOutputs, null, 2) : String(stepOutputs)}
                            </pre>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Final Response Display */}
            {currentExecution.final_response && (
              <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 space-y-3 shadow-sm">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">Final Synthesized Response</h4>
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 text-sm leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap font-sans">
                  {currentExecution.final_response}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-500 space-y-3">
            <Bot className="w-12 h-12 text-slate-300 dark:text-slate-600" />
            <p className="text-sm">Enter an objective on the left to launch an autonomous agent task.</p>
          </div>
        )}
      </div>
    </div>
  );
};
export default AgentStudioView;
