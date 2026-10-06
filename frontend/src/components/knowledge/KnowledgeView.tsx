import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import { Source, DocumentChunk } from '../../types';
import {
  UploadCloud,
  Globe,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  RotateCw,
  Trash2,
  Eye,
  X,
  Database,
  Ban,
  Layers,
} from 'lucide-react';

export const KnowledgeView: React.FC = () => {
  const { currentWorkspace } = useAuth();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'upload' | 'website'>('upload');

  // File Upload State
  const [fileToUpload, setFileToUpload] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  // URL Source State
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [websiteTitle, setWebsiteTitle] = useState('');
  const [isSubmittingUrl, setIsSubmittingUrl] = useState(false);

  // Inspector Modal
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [inspectedChunks, setInspectedChunks] = useState<DocumentChunk[]>([]);
  const [loadingChunks, setLoadingChunks] = useState(false);

  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchSources = useCallback(async () => {
    if (!currentWorkspace) return;
    try {
      const data = await api.listSources(currentWorkspace.id);
      setSources(data);
    } catch (err: any) {
      console.error('Failed to fetch sources:', err);
    } finally {
      setLoading(false);
    }
  }, [currentWorkspace?.id]);

  useEffect(() => {
    fetchSources();
    const interval = setInterval(fetchSources, 4000);
    return () => clearInterval(interval);
  }, [fetchSources]);

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !fileToUpload) return;
    setIsUploading(true);
    setMessage(null);
    try {
      await api.uploadFileSource(currentWorkspace.id, fileToUpload, fileTitle || fileToUpload.name);
      setMessage({ text: 'File uploaded and scheduled for ingestion.', type: 'success' });
      setFileToUpload(null);
      setFileTitle('');
      await fetchSources();
    } catch (err: any) {
      setMessage({ text: `Upload failed: ${err.message}`, type: 'error' });
    } finally {
      setIsUploading(false);
    }
  };

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !websiteUrl.trim()) return;
    setIsSubmittingUrl(true);
    setMessage(null);
    try {
      await api.submitUrlSource(currentWorkspace.id, websiteUrl.trim(), websiteTitle || undefined);
      setMessage({ text: 'Website URL queued for ingestion.', type: 'success' });
      setWebsiteUrl('');
      setWebsiteTitle('');
      await fetchSources();
    } catch (err: any) {
      setMessage({ text: `URL submission failed: ${err.message}`, type: 'error' });
    } finally {
      setIsSubmittingUrl(false);
    }
  };

  const handleRetry = async (sourceId: string) => {
    if (!currentWorkspace) return;
    try {
      await api.retryIngestion(currentWorkspace.id, sourceId);
      setMessage({ text: 'Ingestion retry triggered.', type: 'success' });
      await fetchSources();
    } catch (err: any) {
      setMessage({ text: `Retry failed: ${err.message}`, type: 'error' });
    }
  };

  const handleCancel = async (sourceId: string) => {
    if (!currentWorkspace) return;
    if (!confirm('Cancel this ingestion?')) return;
    try {
      await api.cancelSource(currentWorkspace.id, sourceId);
      setMessage({ text: 'Ingestion cancelled.', type: 'success' });
      await fetchSources();
    } catch (err: any) {
      setMessage({ text: `Cancel failed: ${err.message}`, type: 'error' });
    }
  };

  const handleDelete = async (sourceId: string) => {
    if (!currentWorkspace) return;
    if (!confirm('Delete this source and purge its embeddings?')) return;
    try {
      await api.deleteSource(currentWorkspace.id, sourceId);
      setMessage({ text: 'Source deleted.', type: 'success' });
      setSources((prev) => prev.filter((s) => s.id !== sourceId));
    } catch (err: any) {
      setMessage({ text: `Delete failed: ${err.message}`, type: 'error' });
    }
  };

  // FIX: load chunks via the dedicated /chunks endpoint instead of reading
  // from source.documents[0].chunks (which is never populated in SourceResponse)
  const inspectSource = async (source: Source) => {
    if (!currentWorkspace) return;
    setSelectedSource(source);
    setInspectedChunks([]);

    if (source.status !== 'completed') return;

    setLoadingChunks(true);
    try {
      const chunks = await api.getSourceChunks(currentWorkspace.id, source.id);
      setInspectedChunks(chunks);
    } catch (err) {
      console.error('Failed to load chunks:', err);
    } finally {
      setLoadingChunks(false);
    }
  };

  // Close modal and reset chunk state
  const closeModal = () => {
    setSelectedSource(null);
    setInspectedChunks([]);
    setLoadingChunks(false);
  };

  if (!currentWorkspace) {
    return (
      <div className="p-8 text-center text-slate-500 dark:text-slate-400">
        Select a workspace to view knowledge sources.
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight flex items-center space-x-3">
            <Database className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
            <span>Knowledge Ingestion Hub</span>
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Upload PDF, CSV, text files and crawl verified web pages into partitioned vector storage.
          </p>
        </div>
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

      {/* Ingestion Actions Tabs */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center space-x-4 border-b border-slate-200 dark:border-slate-800 pb-4 mb-6">
          <button
            onClick={() => setActiveTab('upload')}
            className={`flex items-center space-x-2 pb-2 text-sm font-semibold transition-colors border-b-2 ${
              activeTab === 'upload'
                ? 'border-indigo-600 text-indigo-600 dark:border-indigo-500 dark:text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <UploadCloud className="w-4 h-4" />
            <span>Upload Document</span>
          </button>

          <button
            onClick={() => setActiveTab('website')}
            className={`flex items-center space-x-2 pb-2 text-sm font-semibold transition-colors border-b-2 ${
              activeTab === 'website'
                ? 'border-indigo-600 text-indigo-600 dark:border-indigo-500 dark:text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Globe className="w-4 h-4" />
            <span>Crawl Website URL</span>
          </button>
        </div>

        {activeTab === 'upload' ? (
          <form onSubmit={handleFileUpload} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Custom Title (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Q3 Financial Report"
                  value={fileTitle}
                  onChange={(e) => setFileTitle(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Select File (PDF, CSV, TXT — max 20MB)
                </label>
                <input
                  type="file"
                  required
                  accept=".pdf,.csv,.txt,.md"
                  onChange={(e) => setFileToUpload(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-500 dark:text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 dark:file:bg-indigo-950 file:text-indigo-600 dark:file:text-indigo-400 hover:file:bg-indigo-100 dark:hover:file:bg-indigo-900 cursor-pointer"
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={isUploading || !fileToUpload}
                className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-all disabled:opacity-50 shadow-md shadow-indigo-600/20"
              >
                <UploadCloud className="w-4 h-4" />
                <span>{isUploading ? 'Uploading...' : 'Upload & Ingest'}</span>
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleUrlSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Website Title (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Documentation Overview"
                  value={websiteTitle}
                  onChange={(e) => setWebsiteTitle(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Web Page URL
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://example.com/docs/overview"
                  value={websiteUrl}
                  onChange={(e) => setWebsiteUrl(e.target.value)}
                  className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={isSubmittingUrl || !websiteUrl}
                className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-all disabled:opacity-50 shadow-md shadow-indigo-600/20"
              >
                <Globe className="w-4 h-4" />
                <span>{isSubmittingUrl ? 'Fetching & Parsing...' : 'Crawl & Ingest URL'}</span>
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Sources List Table */}
      <div className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-900 dark:text-white text-base">Knowledge Sources</span>
            <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded-full">
              {sources.length} total
            </span>
          </div>
          <button
            onClick={fetchSources}
            className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200 flex items-center space-x-1"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-500 dark:text-slate-400">
            Loading knowledge sources...
          </div>
        ) : sources.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            No sources yet. Upload a document or submit a URL to begin.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-xs uppercase font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-3.5">Title &amp; Source</th>
                  <th className="px-6 py-3.5">Type</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Chunks</th>
                  <th className="px-6 py-3.5">Created</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200/70 dark:divide-slate-800/60">
                {sources.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50 dark:hover:bg-slate-850/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-slate-900 dark:text-white flex items-center space-x-2">
                        <FileText className="w-4 h-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0" />
                        <span className="truncate max-w-xs">{s.title || s.name || 'Untitled Source'}</span>
                      </div>
                      {/* FIX: error_message now comes directly from SourceResponse (not buried in metadata) */}
                      {s.error_message && (
                        <div className="text-xs text-rose-600 dark:text-rose-400 mt-1 flex items-center space-x-1">
                          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                          <span className="truncate max-w-sm">{s.error_message}</span>
                        </div>
                      )}
                    </td>

                    <td className="px-6 py-4 text-xs">
                      <span className="uppercase font-mono bg-slate-100 dark:bg-slate-950 px-2 py-1 rounded text-slate-700 dark:text-slate-400 border border-slate-200 dark:border-slate-800">
                        {s.source_type}
                      </span>
                    </td>

                    <td className="px-6 py-4">
                      {s.status === 'completed' && (
                        <span className="inline-flex items-center space-x-1.5 text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/40 px-2.5 py-1 rounded-full">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Indexed</span>
                        </span>
                      )}
                      {(s.status === 'pending' || s.status === 'processing') && (
                        <span className="inline-flex items-center space-x-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/40 px-2.5 py-1 rounded-full">
                          <Clock className="w-3.5 h-3.5 animate-spin" />
                          <span>{s.status === 'pending' ? 'Pending' : 'Processing…'}</span>
                        </span>
                      )}
                      {s.status === 'failed' && (
                        <span className="inline-flex items-center space-x-1.5 text-xs text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/40 px-2.5 py-1 rounded-full">
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>Failed</span>
                        </span>
                      )}
                      {s.status === 'cancelled' && (
                        <span className="inline-flex items-center space-x-1.5 text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-2.5 py-1 rounded-full">
                          <Ban className="w-3.5 h-3.5 text-slate-500" />
                          <span>Cancelled</span>
                        </span>
                      )}
                    </td>

                    {/* FIX: chunk_count is now a top-level field on SourceResponse, not nested in documents */}
                    <td className="px-6 py-4 text-xs text-slate-600 dark:text-slate-300">
                      {s.status === 'completed' ? (
                        <span className="inline-flex items-center space-x-1 text-emerald-700 dark:text-emerald-400">
                          <Layers className="w-3.5 h-3.5" />
                          <span>{s.chunk_count} chunk{s.chunk_count !== 1 ? 's' : ''}</span>
                        </span>
                      ) : s.status === 'processing' || s.status === 'pending' ? (
                        <span className="text-amber-500 dark:text-amber-400">Processing…</span>
                      ) : s.status === 'failed' ? (
                        <span className="text-rose-500">—</span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    <td className="px-6 py-4 text-xs text-slate-500 dark:text-slate-400">
                      {new Date(s.created_at).toLocaleDateString()}
                    </td>

                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => inspectSource(s)}
                        title="Inspect Chunks"
                        className="p-1.5 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white bg-slate-100 hover:bg-slate-200 dark:bg-slate-950 dark:hover:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-800 transition-colors"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>

                      {(s.status === 'pending' || s.status === 'processing') && (
                        <button
                          onClick={() => handleCancel(s.id)}
                          title="Cancel Ingestion"
                          className="p-1.5 text-amber-600 hover:text-amber-700 bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 rounded-lg border border-amber-200 dark:border-amber-800/60 transition-colors"
                        >
                          <Ban className="w-3.5 h-3.5" />
                        </button>
                      )}

                      {(s.status === 'failed' || s.status === 'cancelled') && (
                        <button
                          onClick={() => handleRetry(s.id)}
                          title="Retry Ingestion"
                          className="p-1.5 text-amber-600 dark:text-amber-400 bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 rounded-lg border border-amber-200 dark:border-amber-800/60 transition-colors"
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                        </button>
                      )}

                      <button
                        onClick={() => handleDelete(s.id)}
                        title="Delete Source"
                        className="p-1.5 text-slate-400 hover:text-rose-600 dark:text-slate-500 dark:hover:text-rose-400 bg-slate-100 hover:bg-rose-50 dark:bg-slate-950 dark:hover:bg-rose-950/40 rounded-lg border border-slate-200 dark:border-slate-800 hover:border-rose-200 dark:hover:border-rose-900 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Source Inspector Modal */}
      {selectedSource && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal header */}
            <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-slate-900 dark:text-white text-base truncate max-w-xl">
                  {selectedSource.title || selectedSource.name}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  ID: <span className="font-mono">{selectedSource.id}</span>{' '}
                  · Type: <span className="uppercase font-mono">{selectedSource.source_type}</span>
                </p>
              </div>
              <button
                onClick={closeModal}
                className="text-slate-400 hover:text-slate-900 dark:hover:text-white p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6">
              {/* Status overview */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400">Status</span>
                  <div className="font-bold text-slate-900 dark:text-white uppercase mt-0.5">
                    {selectedSource.status}
                  </div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400">Chunks Indexed</span>
                  <div className="font-bold text-indigo-600 dark:text-indigo-400 mt-0.5">
                    {selectedSource.status === 'completed'
                      ? selectedSource.chunk_count
                      : selectedSource.status === 'processing' || selectedSource.status === 'pending'
                      ? '…'
                      : '—'}
                  </div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400">Characters</span>
                  <div className="font-bold text-slate-900 dark:text-white mt-0.5">
                    {selectedSource.metadata?.total_characters != null
                      ? Number(selectedSource.metadata.total_characters).toLocaleString()
                      : '—'}
                  </div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800">
                  <span className="text-slate-400">File Size</span>
                  <div className="font-bold text-slate-900 dark:text-white mt-0.5">
                    {selectedSource.metadata?.file_size != null
                      ? `${(Number(selectedSource.metadata.file_size) / 1024).toFixed(1)} KB`
                      : '—'}
                  </div>
                </div>
              </div>

              {/* Error message if failed */}
              {selectedSource.status === 'failed' && selectedSource.error_message && (
                <div className="p-4 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 rounded-xl text-xs text-rose-700 dark:text-rose-300 flex items-start space-x-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Ingestion Error: </span>
                    {selectedSource.error_message}
                  </div>
                </div>
              )}

              {/* Chunks section */}
              <div>
                <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-3 flex items-center space-x-2">
                  <Layers className="w-4 h-4 text-indigo-500" />
                  <span>Extracted &amp; Indexed Chunks</span>
                  {inspectedChunks.length > 0 && (
                    <span className="text-xs font-normal text-slate-500">({inspectedChunks.length} loaded)</span>
                  )}
                </h4>

                {selectedSource.status === 'pending' || selectedSource.status === 'processing' ? (
                  <div className="p-6 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/40 rounded-xl text-xs text-amber-700 dark:text-amber-400 text-center">
                    <Clock className="w-5 h-5 mx-auto mb-2 animate-spin" />
                    Ingestion is in progress — chunks will appear once completed.
                  </div>
                ) : loadingChunks ? (
                  <div className="p-6 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-500 text-center">
                    Loading chunks…
                  </div>
                ) : inspectedChunks.length > 0 ? (
                  <div className="space-y-3">
                    {inspectedChunks.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-xs space-y-2"
                      >
                        <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                          <span className="font-mono text-indigo-600 dark:text-indigo-400 font-semibold">
                            Chunk #{chunk.chunk_index}
                          </span>
                          <span>{chunk.char_count.toLocaleString()} chars</span>
                          {chunk.page_number != null && (
                            <span>Page {chunk.page_number}</span>
                          )}
                        </div>
                        {/* FIX: field name is `content`, not `text_content` */}
                        <p className="text-slate-800 dark:text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap bg-white dark:bg-slate-900/60 p-3 rounded-lg border border-slate-200 dark:border-slate-800/80">
                          {chunk.content}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-500 text-center">
                    {selectedSource.status === 'failed'
                      ? 'No chunks were created — ingestion failed before indexing.'
                      : selectedSource.status === 'cancelled'
                      ? 'Ingestion was cancelled before chunks were created.'
                      : 'No chunks found for this source.'}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeView;
