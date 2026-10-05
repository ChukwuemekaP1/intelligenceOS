// Core Types for IntelligenceOS Frontend

export type UserRole = 'owner' | 'admin' | 'member' | 'viewer';

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  role?: UserRole;
}

export type SourceType = 'file' | 'url' | 'structured' | 'image';
export type SourceStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  text_content: string;
  char_count: number;
  page_number?: number | null;
  metadata?: Record<string, any>;
}

export interface Document {
  id: string;
  source_id: string;
  title: string;
  char_count: number;
  chunk_count: number;
  created_at: string;
  chunks?: DocumentChunk[];
}

export interface Source {
  id: string;
  workspace_id: string;
  title: string;
  source_type: SourceType;
  mime_type?: string | null;
  status: SourceStatus;
  error_message?: string | null;
  raw_file_size?: number | null;
  created_at: string;
  updated_at: string;
  documents?: Document[];
}

export interface Citation {
  source_id: string;
  document_id?: string;
  title: string;
  chunk_index?: number;
  page_number?: number | null;
  similarity_score?: number;
  rerank_score?: number | null;
  snippet?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: Citation[];
  metadata?: Record<string, any>;
  created_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
  messages?: Message[];
}

export interface ToolExecutionStep {
  step_number?: number;
  step_index?: number;
  thought?: string;
  action?: string;
  tool_name?: string | null;
  status?: 'success' | 'error' | string;
  inputs?: Record<string, any>;
  outputs?: Record<string, any>;
  tool_input?: any;
  tool_result?: any;
  duration_ms?: number;
  error?: string | null;
}

export interface AgentExecution {
  execution_id: string;
  workspace_id: string;
  conversation_id?: string | null;
  query?: string;
  status: 'completed' | 'failed' | 'timeout' | string;
  steps?: ToolExecutionStep[];
  trace?: ToolExecutionStep[];
  steps_count?: number;
  final_response?: string | null;
  total_duration_ms?: number;
  total_latency_ms?: number;
  error?: string | null;
  created_at: string;
}

export interface RetrievalMetrics {
  recall_at_k: Record<number, number>;
  mrr: number;
  ndcg_at_k: Record<number, number>;
}

export interface CitationMetrics {
  precision: number;
  recall: number;
  f1: number;
}

export interface EvaluationRun {
  run_id: string;
  dataset_id: string;
  dataset_name: string;
  dataset_version?: string;
  workspace_id: string;
  config: {
    retrieval_mode: 'semantic' | 'hybrid';
    enable_reranking: boolean;
    initial_top_k?: number;
    final_top_k: number;
    evaluator_mode?: string;
  };
  timestamp: string;
  status: string;
  total_examples: number;
  failures_count?: number;
  mean_recall_at_k: number;
  mean_mrr: number;
  mean_ndcg_at_k: number;
  mean_citation_f1: number;
  mean_answer_relevance?: number | null;
  mean_groundedness?: number | null;
  mean_latency_ms: number;
  failures?: string[];
}

export interface EvaluationDataset {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  example_count: number;
  created_at: string;
}

export interface ExperimentComparison {
  run_a_id: string;
  run_b_id: string;
  dataset_id: string;
  config_diff: Record<string, any>;
  metrics_diff: Record<string, number>;
  timestamp: string;
}

export interface Span {
  span_id: string;
  name: string;
  start_time: number;
  end_time?: number;
  duration_ms?: number;
  status: 'ok' | 'error';
  attributes: Record<string, any>;
}

export interface Trace {
  trace_id: string;
  operation_name: string;
  workspace_id?: string;
  user_id?: string;
  start_time: number;
  end_time?: number;
  duration_ms?: number;
  status: 'ok' | 'error';
  spans: Span[];
}
