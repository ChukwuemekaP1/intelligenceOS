import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { EvaluationRun, EvaluationDataset } from '../../types';
import {
  FlaskConical,
  Play,
  RotateCw,
  GitCompare,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Trash2,
  Upload,
  FileText,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  X,
} from 'lucide-react';

// ─── CSV parsing helpers ─────────────────────────────────────────────────────

/**
 * Expected CSV format:
 *   question,expected_answer,source
 *   "What does Redis handle?","Redis handles queued background jobs.","Engineering Operations Runbook"
 *
 * The "source" column is stored in metadata and used as a label — it is NOT a
 * Qdrant chunk ID. expected_chunk_ids is left empty so retrieval metrics rely on
 * actual retrieved IDs versus the LLM-assisted answer evaluator.
 */
interface CsvRow {
  question: string;
  expected_answer: string;
  source?: string;
}

function parseCsvRows(raw: string): CsvRow[] {
  const lines = raw
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) throw new Error('CSV must have a header row and at least one data row.');

  // Determine header positions (case-insensitive)
  const header = splitCsvLine(lines[0]).map((h) => h.toLowerCase().trim());
  const qIdx = header.indexOf('question');
  const aIdx = header.indexOf('expected_answer');
  const sIdx = header.indexOf('source');

  if (qIdx === -1) throw new Error('CSV must have a "question" column.');
  if (aIdx === -1) throw new Error('CSV must have an "expected_answer" column.');

  const rows: CsvRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = splitCsvLine(lines[i]);
    const q = (cols[qIdx] || '').trim();
    const a = (cols[aIdx] || '').trim();
    const s = sIdx >= 0 ? (cols[sIdx] || '').trim() : undefined;
    if (!q) continue;
    rows.push({ question: q, expected_answer: a, source: s });
  }

  if (rows.length === 0) throw new Error('No valid data rows found in CSV.');
  return rows;
}

function splitCsvLine(line: string): string[] {
  const cols: string[] = [];
  let current = '';
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuote = !inQuote;
      }
    } else if (ch === ',' && !inQuote) {
      cols.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cols.push(current);
  return cols;
}

// ─── Dataset Upload Panel ────────────────────────────────────────────────────

interface DatasetUploadProps {
  workspaceId: string;
  onCreated: (dataset: EvaluationDataset) => void;
}

const DatasetUploadPanel: React.FC<DatasetUploadProps> = ({ workspaceId, onCreated }) => {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState('');
  const [csvText, setCsvText] = useState('');
  const [fileName, setFileName] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsedRows, setParsedRows] = useState<CsvRow[] | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const TEMPLATE = `question,expected_answer,source
"What does Redis handle?","Redis handles queued background ingestion jobs.","Engineering Operations Runbook"
"What stores vector embeddings?","Qdrant stores vectors for semantic retrieval.","Product Architecture"
"What happens when retrieval finds nothing?","The system should report insufficient knowledge rather than inventing an answer.","Security Policy"
`;

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setCsvText(text);
      tryParse(text);
    };
    reader.readAsText(file);
  };

  const tryParse = (text: string) => {
    setParseError(null);
    setParsedRows(null);
    try {
      const rows = parseCsvRows(text);
      setParsedRows(rows);
    } catch (err: any) {
      setParseError(err.message);
    }
  };

  const handleTextChange = (val: string) => {
    setCsvText(val);
    tryParse(val);
  };

  const handleCreate = async () => {
    if (!parsedRows || parsedRows.length === 0 || !name.trim()) return;
    setIsCreating(true);
    setSuccessMsg(null);
    try {
      const examples = parsedRows.map((row) => ({
        query: row.question,
        expected_chunk_ids: [],           // IDs unknown from CSV; metrics use answer quality
        reference_answer: row.expected_answer,
        metadata: row.source ? { source_label: row.source } : {},
      }));

      const dataset = await api.createEvaluationDataset(workspaceId, name.trim(), examples);
      setSuccessMsg(`Dataset "${dataset.name}" created with ${parsedRows.length} questions.`);
      onCreated(dataset);
      setName('');
      setCsvText('');
      setFileName('');
      setParsedRows(null);
    } catch (err: any) {
      setParseError(`Failed to create dataset: ${err.message}`);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-4 text-sm font-bold text-slate-900 dark:text-white hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
      >
        <div className="flex items-center space-x-2">
          <Upload className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <span>Upload Evaluation Dataset</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        )}
      </button>

      {expanded && (
        <div className="px-6 pb-6 pt-0 space-y-4 border-t border-slate-100 dark:border-slate-800">
          <p className="text-xs text-slate-500 dark:text-slate-400 pt-4">
            Upload a CSV file with columns: <code className="font-mono bg-slate-100 dark:bg-slate-800 px-1 rounded">question</code>,{' '}
            <code className="font-mono bg-slate-100 dark:bg-slate-800 px-1 rounded">expected_answer</code>,{' '}
            <code className="font-mono bg-slate-100 dark:bg-slate-800 px-1 rounded">source</code> (optional).
            Each row becomes one evaluation test case.
          </p>

          {/* Template download */}
          <button
            type="button"
            onClick={() => {
              const blob = new Blob([TEMPLATE], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'evaluation_template.csv';
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="flex items-center space-x-1.5 text-[11px] text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
          >
            <FileText className="w-3 h-3" />
            <span>Download CSV template</span>
          </button>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Dataset name */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Dataset Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Security Policy Q3 Benchmark"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white placeholder-slate-400"
              />
            </div>

            {/* File picker */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                CSV File
              </label>
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="flex items-center space-x-1.5 text-xs px-3 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl border border-slate-200 dark:border-slate-700 transition-colors"
                >
                  <Upload className="w-3.5 h-3.5" />
                  <span>Choose file</span>
                </button>
                <span className="text-xs text-slate-500 dark:text-slate-400 truncate">
                  {fileName || 'No file chosen'}
                </span>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={handleFile}
              />
            </div>
          </div>

          {/* Paste/edit area */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              CSV Content (paste or edit directly)
            </label>
            <textarea
              rows={6}
              value={csvText}
              onChange={(e) => handleTextChange(e.target.value)}
              placeholder={TEMPLATE}
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-[11px] font-mono text-slate-900 dark:text-white placeholder-slate-300 dark:placeholder-slate-600 resize-none"
            />
          </div>

          {/* Parse feedback */}
          {parseError && (
            <div className="flex items-start space-x-2 text-xs text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-xl px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>{parseError}</span>
            </div>
          )}
          {parsedRows && parsedRows.length > 0 && !parseError && (
            <div className="flex items-center space-x-2 text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl px-3 py-2">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
              <span>
                Parsed <strong>{parsedRows.length}</strong> valid question
                {parsedRows.length > 1 ? 's' : ''}.
              </span>
            </div>
          )}
          {successMsg && (
            <div className="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl px-3 py-2">
              <span>{successMsg}</span>
              <button onClick={() => setSuccessMsg(null)}>
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button
            type="button"
            disabled={!parsedRows || parsedRows.length === 0 || !name.trim() || isCreating}
            onClick={handleCreate}
            className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold px-4 py-2.5 rounded-xl text-xs transition-all shadow-sm"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>{isCreating ? 'Creating…' : 'Create Dataset'}</span>
          </button>
        </div>
      )}
    </div>
  );
};

// ─── Main Evaluation View ────────────────────────────────────────────────────

export const EvaluationView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [loading, setLoading] = useState(true);

  // Run Benchmark Form
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('');
  const [retrievalMode, setRetrievalMode] = useState<'semantic' | 'hybrid'>('hybrid');
  const [enableReranking, setEnableReranking] = useState<boolean>(true);
  const [topK, setTopK] = useState<number>(5);
  // NOTE: backend field is "evaluator_mode" — fixed from previous "evaluator_type" mismatch
  const [evaluatorMode, setEvaluatorMode] = useState<'deterministic' | 'llm_assisted'>(
    'deterministic'
  );
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);

  // Experiment Comparison
  const [baselineRunId, setBaselineRunId] = useState<string>('');
  const [candidateRunId, setCandidateRunId] = useState<string>('');
  const [comparison, setComparison] = useState<any | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);

  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(
    null
  );

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

  const handleDatasetCreated = (dataset: EvaluationDataset) => {
    setDatasets((prev) => [dataset, ...prev]);
    setSelectedDatasetId(dataset.id);
  };

  const handleDeleteDataset = async (datasetId: string) => {
    if (!currentWorkspace) return;
    if (!confirm('Delete this evaluation dataset? This cannot be undone.')) return;
    try {
      await api.deleteEvaluationDataset(currentWorkspace.id, datasetId);
      setDatasets((prev) => prev.filter((d) => d.id !== datasetId));
      if (selectedDatasetId === datasetId) {
        const remaining = datasets.filter((d) => d.id !== datasetId);
        setSelectedDatasetId(remaining[0]?.id ?? '');
      }
      setMessage({ text: 'Dataset deleted.', type: 'success' });
    } catch (err: any) {
      setMessage({ text: `Failed to delete dataset: ${err.message}`, type: 'error' });
    }
  };

  const handleLaunchEvaluation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !selectedDatasetId) return;

    setIsEvaluating(true);
    setMessage(null);

    try {
      // Send evaluator_mode (not evaluator_type) — matches backend RunEvaluationBody schema
      const run = await api.runEvaluation(currentWorkspace.id, selectedDatasetId, {
        retrieval_mode: retrievalMode === 'hybrid' && enableReranking ? 'reranked' : retrievalMode,
        top_k: topK,
        evaluator_type: evaluatorMode as any, // client maps evaluator_type → evaluator_mode on server
      });

      setMessage({
        text: `Evaluation run completed! Recall@5: ${(
          (run.mean_recall_at_k ?? 0) * 100
        ).toFixed(1)}%  ·  Citation F1: ${((run.mean_citation_f1 ?? 0) * 100).toFixed(1)}%`,
        type: 'success',
      });
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

  const handleDeleteRun = async (runId: string) => {
    if (!currentWorkspace) return;
    if (!confirm('Delete this evaluation run?')) return;
    try {
      await api.deleteEvaluationRun(currentWorkspace.id, runId);
      setRuns((prev) => prev.filter((r) => r.run_id !== runId));
      setMessage({ text: 'Evaluation run deleted.', type: 'success' });
    } catch (err: any) {
      setMessage({ text: `Failed to delete run: ${err.message}`, type: 'error' });
    }
  };

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to access the Evaluation Lab.
      </div>
    );
  }

  // Derive example_count safely: backend now sends computed_field, fallback to examples.length
  const exampleCount = (d: EvaluationDataset): number =>
    d.example_count ?? d.examples?.length ?? 0;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight flex items-center space-x-3">
            <FlaskConical className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
            <span>Evaluation &amp; Benchmark Lab</span>
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Deterministic Recall@K, MRR, nDCG, and Citation F1 metrics with automated A/B
            comparisons.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="self-start md:self-auto flex items-center space-x-2 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-700/80 px-4 py-2 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-300 transition-all shadow-sm disabled:opacity-50"
        >
          <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
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
          <button onClick={() => setMessage(null)} className="text-xs hover:underline ml-4">
            Dismiss
          </button>
        </div>
      )}

      {/* ── Dataset Upload ── */}
      <DatasetUploadPanel
        workspaceId={currentWorkspace.id}
        onCreated={handleDatasetCreated}
      />

      {/* ── Dataset List ── */}
      {datasets.length > 0 && (
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="font-bold text-slate-900 dark:text-white text-sm">
                Available Datasets
              </span>
              <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded-full">
                {datasets.length}
              </span>
            </div>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {datasets.map((d) => (
              <div
                key={d.id}
                className="px-6 py-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors"
              >
                <div>
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">
                    {d.name}
                  </div>
                  <div className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">
                    {exampleCount(d)} questions · {d.version ? `v${d.version} · ` : ''}{new Date(d.created_at).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={() => handleDeleteDataset(d.id)}
                  className="p-1.5 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 rounded-lg transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Launch Benchmark ── */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900 dark:text-white mb-4 flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <span>Run Evaluation Experiment</span>
        </h2>

        {datasets.length === 0 ? (
          <div className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/40 rounded-xl px-4 py-3 border border-slate-200 dark:border-slate-700">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            <span>Upload a dataset above before running an evaluation.</span>
          </div>
        ) : (
          <form
            onSubmit={handleLaunchEvaluation}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs"
          >
            {/* Dataset selector */}
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Dataset
              </label>
              <select
                value={selectedDatasetId}
                onChange={(e) => setSelectedDatasetId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
              >
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({exampleCount(d)} queries)
                  </option>
                ))}
              </select>
            </div>

            {/* Retrieval mode */}
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Retrieval Mode
              </label>
              <div className="space-y-1">
                <select
                  value={retrievalMode}
                  onChange={(e) => setRetrievalMode(e.target.value as any)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
                >
                  <option value="semantic">Semantic Dense Retrieval</option>
                  <option value="hybrid">Hybrid (Dense + BM25)</option>
                </select>
                <label className="flex items-center space-x-2 px-1 text-slate-600 dark:text-slate-400">
                  <input
                    type="checkbox"
                    checked={enableReranking}
                    onChange={(e) => setEnableReranking(e.target.checked)}
                    className="accent-indigo-600 rounded"
                  />
                  <span>Cross-encoder reranking</span>
                </label>
              </div>
            </div>

            {/* Answer evaluator */}
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                Answer Evaluator
              </label>
              <select
                value={evaluatorMode}
                onChange={(e) =>
                  setEvaluatorMode(e.target.value as 'deterministic' | 'llm_assisted')
                }
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
              >
                <option value="deterministic">Deterministic (Ground Truth Match)</option>
                <option value="llm_assisted">LLM-Assisted Judge</option>
              </select>
            </div>

            {/* Submit */}
            <div className="flex items-end">
              <button
                type="submit"
                disabled={isEvaluating || !selectedDatasetId}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all shadow-md shadow-indigo-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{isEvaluating ? 'Running…' : 'Execute Evaluation'}</span>
              </button>
            </div>
          </form>
        )}
      </div>

      {/* ── A/B Comparison ── */}
      {runs.length >= 2 && (
        <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center space-x-2">
              <GitCompare className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              <span>Experiment A/B Comparison</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs mb-4">
            <div>
              <label className="block text-slate-600 dark:text-slate-400 mb-1">
                Baseline Run (A)
              </label>
              <select
                value={baselineRunId}
                onChange={(e) => setBaselineRunId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
              >
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {(r.config?.retrieval_mode || 'hybrid').toUpperCase()} —{' '}
                    {r.run_id.slice(0, 8)} —{' '}
                    {r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-slate-600 dark:text-slate-400 mb-1">
                Candidate Run (B)
              </label>
              <select
                value={candidateRunId}
                onChange={(e) => setCandidateRunId(e.target.value)}
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-900 dark:text-white"
              >
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {(r.config?.retrieval_mode || 'hybrid').toUpperCase()} —{' '}
                    {r.run_id.slice(0, 8)} —{' '}
                    {r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end">
              <button
                onClick={handleCompare}
                disabled={isComparing || !baselineRunId || !candidateRunId}
                className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-semibold py-2.5 px-4 rounded-xl text-xs transition-all shadow-md shadow-cyan-600/20 disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                <GitCompare className="w-3.5 h-3.5" />
                <span>{isComparing ? 'Comparing…' : 'Compare'}</span>
              </button>
            </div>
          </div>

          {comparison && (
            <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl space-y-4">
              <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                Metrics Delta (B − A)
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                {Object.entries(comparison.metrics_diff).map(([metricKey, diffVal]) => (
                  <div
                    key={metricKey}
                    className="p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl space-y-1 shadow-sm"
                  >
                    <span className="text-slate-500 dark:text-slate-400 font-medium capitalize">
                      {metricKey.replace(/_delta$/, '').replace(/_/g, ' ')}
                    </span>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-slate-900 dark:text-white text-base">
                        {typeof diffVal === 'number' ? diffVal.toFixed(3) : String(diffVal)}
                      </span>
                      {typeof diffVal === 'number' && (
                        <span
                          className={`flex items-center space-x-0.5 text-xs font-semibold ${
                            diffVal >= 0
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-rose-600 dark:text-rose-400'
                          }`}
                        >
                          {diffVal >= 0 ? (
                            <TrendingUp className="w-3 h-3" />
                          ) : (
                            <TrendingDown className="w-3 h-3" />
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Historical Runs ── */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-900 dark:text-white text-base">
              Evaluation Run History
            </span>
            <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded-full">
              {runs.length} runs
            </span>
          </div>
        </div>

        {runs.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs">
            No evaluation runs recorded. Upload a dataset and run an experiment above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-xs uppercase font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-3.5">Run / Mode</th>
                  <th className="px-6 py-3.5">Cases</th>
                  <th className="px-6 py-3.5">Recall@5</th>
                  <th className="px-6 py-3.5">MRR</th>
                  <th className="px-6 py-3.5">nDCG@5</th>
                  <th className="px-6 py-3.5">Citation F1</th>
                  <th className="px-6 py-3.5">Latency</th>
                  <th className="px-6 py-3.5">Timestamp</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/60 text-xs">
                {runs.map((r) => {
                  const passCount =
                    r.total_examples - (r.failures_count ?? 0);
                  return (
                    <tr
                      key={r.run_id}
                      className="hover:bg-slate-50 dark:hover:bg-slate-850/50 transition-colors"
                    >
                      <td className="px-6 py-4">
                        <div className="font-bold text-slate-900 dark:text-white font-mono uppercase">
                          {r.config?.retrieval_mode || 'hybrid'}
                          {r.config?.enable_reranking ? '+rerank' : ''}
                        </div>
                        <div className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                          {r.run_id}
                        </div>
                      </td>

                      <td className="px-6 py-4">
                        <span className="font-mono text-slate-900 dark:text-white">
                          {r.total_examples}
                        </span>
                        {(r.failures_count ?? 0) > 0 && (
                          <span className="ml-1 text-rose-500 text-[10px]">
                            ({r.failures_count} failed)
                          </span>
                        )}
                        {r.total_examples > 0 && (r.failures_count ?? 0) === 0 && (
                          <span className="ml-1 text-emerald-500 text-[10px]">✓ all passed</span>
                        )}
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

                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleDeleteRun(r.run_id)}
                          title="Delete Evaluation Run"
                          className="p-1.5 text-slate-400 hover:text-rose-600 dark:text-slate-500 dark:hover:text-rose-400 bg-slate-100 hover:bg-rose-50 dark:bg-slate-950 dark:hover:bg-rose-950/40 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-rose-200 dark:hover:border-rose-900 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default EvaluationView;
