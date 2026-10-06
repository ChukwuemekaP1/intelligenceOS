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
  Trash2,
  AlertCircle,
  WifiOff,
} from 'lucide-react';

// ─── Realistic example objectives ──────────────────────────────────────────

const EXAMPLE_OBJECTIVES = [
  {
    label: 'Incident readiness assessment',
    prompt:
      'Analyze the selected documents and produce an incident-readiness assessment. Identify the most important operational risks, explain the documented mitigation for each, and identify gaps where the documentation does not provide a clear recovery procedure.',
  },
  {
    label: 'Security controls audit',
    prompt:
      'Find all documented security controls in the workspace knowledge base. Group them by category (access control, encryption, monitoring, incident response). For each category, cite the specific source and note any controls that appear incomplete or contradictory.',
  },
  {
    label: 'Compare ingestion failure procedures',
    prompt:
      'Compare the ingestion failure and retry procedures documented across the available sources. Identify any operational gaps — steps where the documentation does not specify a clear owner, timeout, or recovery path.',
  },
  {
    label: 'Calculate risk exposure score',
    prompt:
      'Retrieve the documented risk ratings from the knowledge base. Use the calculator to compute the weighted average risk exposure score across all identified risks. Show your calculation step by step.',
  },
];

// ─── Tool metadata ──────────────────────────────────────────────────────────

const AVAILABLE_TOOLS = [
  {
    name: 'knowledge_search',
    label: 'Knowledge Search',
    desc: 'Retrieves grounded context from workspace documents via hybrid vector + BM25 retrieval',
    icon: Database,
    alwaysAvailable: true,
  },
  {
    name: 'read_only_sql',
    label: 'Read-Only SQL',
    desc: 'Safely queries relational data — mutations (INSERT/UPDATE/DELETE/DROP) are blocked',
    icon: Code,
    alwaysAvailable: true,
  },
  {
    name: 'calculator',
    label: 'Safe Calculator',
    desc: 'Evaluates arithmetic and math expressions via AST parser — no eval(), no code execution',
    icon: Calculator,
    alwaysAvailable: true,
  },
  {
    name: 'web_search',
    label: 'Web Search',
    desc: 'Queries external real-time facts. Requires WEB_SEARCH_PROVIDER to be configured — reports Unavailable otherwise.',
    icon: Search,
    alwaysAvailable: false, // surfaced as unavailable when provider = mock
  },
];

// ─── Component ──────────────────────────────────────────────────────────────

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
  const [showExamples, setShowExamples] = useState(false);

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
    setCurrentExecution(run);
    try {
      const full = await api.getAgentExecution(currentWorkspace.id, run.execution_id);
      if (full) setCurrentExecution(full);
    } catch (err) {
      console.warn('Could not load detailed trace for agent run:', err);
    }
  };

  const handleDeleteRun = async (executionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentWorkspace) return;
    if (!confirm('Delete this agent execution log?')) return;
    try {
      await api.deleteAgentExecution(currentWorkspace.id, executionId);
      setHistory((prev) => prev.filter((r) => r.execution_id !== executionId));
      if (currentExecution?.execution_id === executionId) setCurrentExecution(null);
    } catch (err: any) {
      setError(`Failed to delete execution: ${err.message}`);
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
              Multi-tool ReAct loop: agent reasons → selects tool → executes → observes → repeats until final answer.
            </p>
          </div>

          <form onSubmit={handleExecute} className="space-y-4">
            {/* Objective textarea */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Agent Objective
                </label>
                <button
                  type="button"
                  onClick={() => setShowExamples((v) => !v)}
                  className="text-[11px] text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                >
                  {showExamples ? 'Hide examples' : 'Show examples'}
                </button>
              </div>

              {/* Example objectives panel */}
              {showExamples && (
                <div className="mb-2 space-y-1.5 p-3 bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-700 rounded-xl">
                  {EXAMPLE_OBJECTIVES.map((ex) => (
                    <button
                      key={ex.label}
                      type="button"
                      onClick={() => { setPrompt(ex.prompt); setShowExamples(false); }}
                      className="w-full text-left text-xs px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 text-slate-700 dark:text-slate-300 transition-colors"
                    >
                      <span className="font-semibold text-indigo-600 dark:text-indigo-400 block mb-0.5">
                        {ex.label}
                      </span>
                      <span className="text-[10px] text-slate-500 dark:text-slate-400 line-clamp-2">
                        {ex.prompt.slice(0, 120)}…
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <textarea
                rows={5}
                required
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={
                  'e.g. Analyze the selected security and operations documents. Identify the five most important operational risks, explain their documented mitigations, and cite the supporting sources.'
                }
                className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl p-3 text-xs text-slate-900 dark:text-white focus:outline-none focus:border-purple-500 placeholder-slate-400 dark:placeholder-slate-500 leading-relaxed resize-none shadow-sm"
              />
            </div>

            {/* Tool sandbox */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
                Allowed Tools Sandbox ({selectedTools.length} enabled)
              </label>
              <div className="space-y-2">
                {AVAILABLE_TOOLS.map((t) => {
                  const Icon = t.icon;
                  const isChecked = selectedTools.includes(t.name);
                  // Web search surfaces an "unavailable" badge — still toggleable, agent will
                  // receive an honest "unavailable" result if it tries to call it
                  const isWebSearch = t.name === 'web_search';

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
                        <Icon
                          className={`w-3.5 h-3.5 ${
                            isChecked
                              ? 'text-purple-600 dark:text-purple-400'
                              : 'text-slate-400 dark:text-slate-500'
                          }`}
                        />
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-900 dark:text-white flex items-center space-x-1.5">
                            <span>{t.label}</span>
                            {isWebSearch && (
                              <span
                                title="Web search requires WEB_SEARCH_PROVIDER to be configured"
                                className="inline-flex items-center space-x-0.5 text-[9px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800 font-semibold uppercase tracking-wide"
                              >
                                <WifiOff className="w-2.5 h-2.5" />
                                <span>Needs config</span>
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 truncate max-w-[200px]">
                            {t.desc}
                          </div>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        readOnly
                        className="accent-purple-600 rounded flex-shrink-0"
                      />
                    </div>
                  );
                })}
              </div>

              {/* Web search notice */}
              {selectedTools.includes('web_search') && (
                <div className="mt-2 flex items-start space-x-1.5 text-[10px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg px-2.5 py-2">
                  <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                  <span>
                    Web Search is enabled but will report{' '}
                    <strong>Unavailable</strong> unless{' '}
                    <code className="font-mono">WEB_SEARCH_PROVIDER</code> is set to a real
                    provider (e.g. <code className="font-mono">brave</code>,{' '}
                    <code className="font-mono">tavily</code>). No fake results will be returned.
                  </span>
                </div>
              )}
            </div>

            {/* Step budget */}
            <div>
              <div className="flex justify-between text-xs mb-1 font-semibold text-slate-700 dark:text-slate-300">
                <span>Max Step Budget</span>
                <span className="font-mono text-purple-600 dark:text-purple-400">
                  {maxSteps} steps
                </span>
              </div>
              <input
                type="range"
                min="2"
                max="10"
                value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value))}
                className="w-full accent-purple-600"
              />
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                Agent will synthesize a best-effort answer if budget is reached before completion.
              </p>
            </div>

            <button
              type="submit"
              disabled={isExecuting || !prompt.trim()}
              className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold py-3 rounded-xl text-xs transition-all shadow-md shadow-purple-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>
                {isExecuting ? 'Agent Reasoning & Executing…' : 'Launch Agent Execution'}
              </span>
            </button>
          </form>

          {error && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-start space-x-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Prior Executions */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/30">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
            <span>Execution Log</span>
            <button
              onClick={fetchHistory}
              className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
            >
              <RotateCw className="w-3 h-3" />
            </button>
          </div>
          <div className="max-h-40 overflow-y-auto space-y-1.5">
            {history.length === 0 ? (
              <div className="text-xs text-slate-400 dark:text-slate-600">
                No past runs in log.
              </div>
            ) : (
              history.map((run) => {
                const title = run.query || run.final_response || 'Agent Run';
                const displayTitle =
                  title.length > 35 ? `${title.slice(0, 35)}…` : title;
                const stepsCount =
                  run.steps_count ?? run.steps?.length ?? run.trace?.length ?? 0;
                return (
                  <div
                    key={run.execution_id}
                    onClick={() => handleSelectRun(run)}
                    className={`group p-2 rounded-xl text-xs cursor-pointer flex items-center justify-between transition-colors ${
                      currentExecution?.execution_id === run.execution_id
                        ? 'bg-purple-50 dark:bg-purple-950/50 border border-purple-200 dark:border-purple-800/60 text-purple-900 dark:text-purple-200 font-medium'
                        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-900'
                    }`}
                  >
                    <div className="truncate max-w-[170px]">{displayTitle}</div>
                    <div className="flex items-center space-x-1.5 flex-shrink-0">
                      <span className="text-[10px] text-slate-400 dark:text-slate-500">
                        {stepsCount} steps
                      </span>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteRun(run.execution_id, e)}
                        title="Delete Execution"
                        className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded transition-opacity"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
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
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    Execution ID:
                  </span>
                  <span className="text-xs font-mono text-purple-600 dark:text-purple-400">
                    {currentExecution.execution_id}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Safe Tool Orchestration Trace
                </h3>
                {currentExecution.query && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-lg line-clamp-2">
                    {currentExecution.query}
                  </p>
                )}
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
                      : currentExecution.status === 'budget_exceeded'
                      ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800'
                      : 'bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{currentExecution.status}</span>
                </div>
              </div>
            </div>

            {/* Execution Steps Timeline */}
            <div className="space-y-4">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>
                  Execution Steps ({stepsList.length})
                </span>
              </h4>

              {stepsList.length === 0 ? (
                <div className="p-4 bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-500 dark:text-slate-400 shadow-sm">
                  {currentExecution.query
                    ? `Task: "${currentExecution.query}" — agent answered directly without calling any tools.`
                    : 'No intermediate tools were called; agent solved request directly.'}
                </div>
              ) : (
                <div className="space-y-3">
                  {stepsList.map((step: ToolExecutionStep, idx: number) => {
                    const stepNum = step.step_index ?? step.step_number ?? idx + 1;
                    const toolName = step.tool_name || step.action || 'tool_step';
                    const stepInputs = step.inputs ?? step.tool_input ?? {};
                    const stepOutputs = step.outputs ?? step.tool_result ?? {};
                    const isSuccess =
                      step.status === 'success' ||
                      (!step.error && step.status !== 'error');

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
                          <p className="text-xs text-slate-600 dark:text-slate-400 italic border-l-2 border-indigo-200 dark:border-indigo-800 pl-2">
                            {step.thought}
                          </p>
                        )}

                        {step.error && (
                          <div className="text-xs text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-lg px-3 py-2">
                            {step.error}
                          </div>
                        )}

                        {/* Inputs and Outputs */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                          <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800/80">
                            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1 font-sans">
                              Tool Input
                            </div>
                            <pre className="text-slate-800 dark:text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
                              {typeof stepInputs === 'object'
                                ? JSON.stringify(stepInputs, null, 2)
                                : String(stepInputs)}
                            </pre>
                          </div>

                          <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800/80">
                            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1 font-sans">
                              Tool Result
                            </div>
                            <pre className="text-slate-800 dark:text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
                              {typeof stepOutputs === 'object'
                                ? JSON.stringify(stepOutputs, null, 2)
                                : String(stepOutputs)}
                            </pre>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Final Response */}
            {currentExecution.final_response && (
              <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 space-y-3 shadow-sm">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span>Final Synthesized Response</span>
                </h4>
                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 text-sm leading-relaxed text-slate-800 dark:text-slate-200 whitespace-pre-wrap font-sans">
                  {currentExecution.final_response}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-500 space-y-4 max-w-md mx-auto">
            <Bot className="w-12 h-12 text-slate-300 dark:text-slate-600" />
            <div>
              <p className="text-sm font-semibold text-slate-600 dark:text-slate-400">
                Enter an objective to launch an autonomous agent task.
              </p>
              <p className="text-xs mt-2 text-slate-400 dark:text-slate-500 leading-relaxed">
                The agent will reason, select tools, execute them, observe results, and iterate
                until it produces a grounded final answer — or reaches the step budget.
              </p>
            </div>
            <div className="w-full pt-2 space-y-2 text-left">
              <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                Example objectives
              </p>
              {EXAMPLE_OBJECTIVES.slice(0, 2).map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  onClick={() => setPrompt(ex.prompt)}
                  className="w-full text-left text-xs px-3 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-indigo-300 dark:hover:border-indigo-700 text-slate-700 dark:text-slate-300 transition-colors shadow-sm"
                >
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400 block mb-0.5">
                    {ex.label}
                  </span>
                  <span className="text-[10px] text-slate-500 dark:text-slate-400 line-clamp-2">
                    {ex.prompt.slice(0, 130)}…
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentStudioView;
