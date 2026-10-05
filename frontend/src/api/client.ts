import {
  User,
  Workspace,
  Source,
  Conversation,
  Message,
  AgentExecution,
  EvaluationDataset,
  EvaluationRun,
  ExperimentComparison,
  Trace,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

export class ApiError extends Error {
  status: number;
  statusText: string;
  fieldErrors?: Record<string, string>;

  constructor(status: number, statusText: string, message: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.fieldErrors = fieldErrors;
  }
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('intelligenceos_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('intelligenceos_token', token);
    } else {
      localStorage.removeItem('intelligenceos_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${BASE_URL}${endpoint}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Clear token on authentication failure
      this.setToken(null);
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      let fieldErrors: Record<string, string> | undefined;

      try {
        const errorData = await response.json();
        if (errorData.detail) {
          if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail;
          } else if (Array.isArray(errorData.detail)) {
            // Pydantic validation errors list: [{ loc: ['body', 'title'], msg: '...', type: '...' }]
            fieldErrors = {};
            const messages = errorData.detail.map((err: any) => {
              const field = Array.isArray(err.loc)
                ? err.loc.filter((l: any) => l !== 'body').join('.')
                : (err.loc || '');
              const msg = err.msg || 'Invalid value';
              if (field) fieldErrors![field] = msg;
              return field ? `${field}: ${msg}` : msg;
            });
            errorMessage = messages.join('; ');
          } else {
            errorMessage = JSON.stringify(errorData.detail);
          }
        }
      } catch {
        // Fallback friendly status messages
        switch (response.status) {
          case 400:
            errorMessage = 'Bad request. Please verify your inputs.';
            break;
          case 401:
            errorMessage = 'Authentication required or session expired.';
            break;
          case 403:
            errorMessage = 'Access denied. You do not have permission for this workspace resource.';
            break;
          case 404:
            errorMessage = 'Requested resource not found.';
            break;
          case 405:
            errorMessage = 'Method not allowed for this endpoint.';
            break;
          case 409:
            errorMessage = 'Conflict with existing resource state.';
            break;
          case 422:
            errorMessage = 'Validation error. Please verify input fields.';
            break;
          case 429:
            errorMessage = 'Rate limit exceeded. Please wait and try again.';
            break;
          case 500:
            errorMessage = 'Internal server error. Please try again later.';
            break;
          case 502:
            errorMessage = 'Bad Gateway. Backend service unreachable.';
            break;
          case 503:
            errorMessage = 'Service temporarily unavailable.';
            break;
          default:
            errorMessage = `Request failed (HTTP ${response.status}: ${response.statusText})`;
        }
      }
      throw new ApiError(response.status, response.statusText, errorMessage, fieldErrors);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // ==================== AUTH ====================
  async login(email: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const data = await this.request<{ access_token: string; token_type: string }>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }
    );
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, password: string, fullName?: string): Promise<User> {
    return this.request<User>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
  }

  async getMe(): Promise<User> {
    return this.request<User>('/api/v1/auth/me');
  }

  // ==================== WORKSPACES ====================
  async listWorkspaces(): Promise<Workspace[]> {
    return this.request<Workspace[]>('/api/v1/workspaces');
  }

  async createWorkspace(name: string, slug?: string): Promise<Workspace> {
    return this.request<Workspace>('/api/v1/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name, slug: slug || name.toLowerCase().replace(/[^a-z0-9]/g, '-') }),
    });
  }

  // ==================== SOURCES ====================
  async listSources(workspaceId: string): Promise<Source[]> {
    return this.request<Source[]>(`/api/v1/workspaces/${workspaceId}/sources`);
  }

  async getSource(workspaceId: string, sourceId: string): Promise<Source> {
    return this.request<Source>(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}`);
  }

  async uploadFileSource(workspaceId: string, file: File, title?: string): Promise<Source> {
    const formData = new FormData();
    formData.append('file', file);
    if (title) {
      formData.append('title', title);
    }
    return this.request<Source>(`/api/v1/workspaces/${workspaceId}/sources/upload`, {
      method: 'POST',
      body: formData,
    });
  }

  async submitUrlSource(workspaceId: string, url: string, title?: string): Promise<Source> {
    return this.request<Source>(`/api/v1/workspaces/${workspaceId}/sources/url`, {
      method: 'POST',
      body: JSON.stringify({ url, title }),
    });
  }

  async retryIngestion(workspaceId: string, sourceId: string): Promise<Source> {
    return this.request<Source>(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}/retry`, {
      method: 'POST',
    });
  }

  async cancelSource(workspaceId: string, sourceId: string): Promise<Source> {
    return this.request<Source>(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}/cancel`, {
      method: 'POST',
    });
  }

  async deleteSource(workspaceId: string, sourceId: string): Promise<void> {
    return this.request<void>(`/api/v1/workspaces/${workspaceId}/sources/${sourceId}`, {
      method: 'DELETE',
    });
  }

  // ==================== CONVERSATIONS & RAG ====================
  async listConversations(workspaceId: string): Promise<Conversation[]> {
    return this.request<Conversation[]>(`/api/v1/workspaces/${workspaceId}/conversations`);
  }

  async createConversation(workspaceId: string, title: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/v1/workspaces/${workspaceId}/conversations`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  }

  async getConversation(workspaceId: string, conversationId: string): Promise<Conversation> {
    return this.request<Conversation>(`/api/v1/workspaces/${workspaceId}/conversations/${conversationId}`);
  }

  async sendMessage(
    workspaceId: string,
    conversationId: string,
    content: string,
    options: {
      retrieval_mode?: 'hybrid' | 'semantic';
      top_k?: number;
      enable_reranking?: boolean;
    } = {}
  ): Promise<Message> {
    const res = await this.request<any>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        body: JSON.stringify({
          question: content,
          retrieval_config: {
            retrieval_mode: options.retrieval_mode ?? 'hybrid',
            final_top_k: options.top_k ?? 5,
            enable_reranking: options.enable_reranking ?? true,
          },
        }),
      }
    );
    if (res.assistant_message) {
      return {
        ...res.assistant_message,
        citations: res.citations || res.assistant_message.citations,
        metadata: res.metrics,
      };
    }
    return res;
  }

  async deleteConversation(workspaceId: string, conversationId: string): Promise<void> {
    return this.request<void>(`/api/v1/workspaces/${workspaceId}/conversations/${conversationId}`, {
      method: 'DELETE',
    });
  }

  // ==================== AGENTS ====================
  async executeAgent(
    workspaceId: string,
    prompt: string,
    options: {
      allowed_tools?: string[];
      max_steps?: number;
    } = {}
  ): Promise<AgentExecution> {
    return this.request<AgentExecution>(`/api/v1/workspaces/${workspaceId}/agent/execute`, {
      method: 'POST',
      body: JSON.stringify({
        query: prompt,
        allowed_tools: options.allowed_tools,
        max_steps: options.max_steps ?? 6,
      }),
    });
  }

  async listAgentExecutions(workspaceId: string): Promise<AgentExecution[]> {
    return this.request<AgentExecution[]>(`/api/v1/workspaces/${workspaceId}/agent/executions`);
  }

  async getAgentExecution(workspaceId: string, executionId: string): Promise<AgentExecution> {
    return this.request<AgentExecution>(`/api/v1/workspaces/${workspaceId}/agent/executions/${executionId}`);
  }

  async deleteAgentExecution(workspaceId: string, executionId: string): Promise<void> {
    return this.request<void>(`/api/v1/workspaces/${workspaceId}/agent/executions/${executionId}`, {
      method: 'DELETE',
    });
  }

  // ==================== EVALUATION ====================
  async listEvaluationDatasets(workspaceId: string): Promise<EvaluationDataset[]> {
    return this.request<EvaluationDataset[]>(`/api/v1/workspaces/${workspaceId}/evaluations/datasets`);
  }

  async createEvaluationDataset(
    workspaceId: string,
    name: string,
    examples: Array<{ query: string; expected_chunk_ids: string[]; reference_answer?: string }>
  ): Promise<EvaluationDataset> {
    return this.request<EvaluationDataset>(`/api/v1/workspaces/${workspaceId}/evaluations/datasets`, {
      method: 'POST',
      body: JSON.stringify({ name, examples }),
    });
  }

  async deleteEvaluationDataset(workspaceId: string, datasetId: string): Promise<void> {
    return this.request<void>(`/api/v1/workspaces/${workspaceId}/evaluations/datasets/${datasetId}`, {
      method: 'DELETE',
    });
  }

  async runEvaluation(
    workspaceId: string,
    datasetId: string,
    options: {
      retrieval_mode: 'semantic' | 'hybrid' | 'reranked';
      top_k?: number;
      evaluator_type?: 'deterministic' | 'llm';
    }
  ): Promise<EvaluationRun> {
    return this.request<EvaluationRun>(`/api/v1/workspaces/${workspaceId}/evaluations/run`, {
      method: 'POST',
      body: JSON.stringify({
        dataset_id: datasetId,
        retrieval_mode: options.retrieval_mode,
        top_k: options.top_k ?? 5,
        evaluator_type: options.evaluator_type ?? 'deterministic',
      }),
    });
  }

  async listEvaluationRuns(workspaceId: string): Promise<EvaluationRun[]> {
    return this.request<EvaluationRun[]>(`/api/v1/workspaces/${workspaceId}/evaluations/runs`);
  }

  async deleteEvaluationRun(workspaceId: string, runId: string): Promise<void> {
    return this.request<void>(`/api/v1/workspaces/${workspaceId}/evaluations/runs/${runId}`, {
      method: 'DELETE',
    });
  }

  async compareExperiments(
    workspaceId: string,
    baselineRunId: string,
    candidateRunId: string
  ): Promise<ExperimentComparison> {
    return this.request<ExperimentComparison>(
      `/api/v1/workspaces/${workspaceId}/evaluations/compare?baseline_id=${baselineRunId}&candidate_id=${candidateRunId}`
    );
  }

  // ==================== OBSERVABILITY / TRACES ====================
  async listTraces(workspaceId: string): Promise<Trace[]> {
    return this.request<Trace[]>(`/api/v1/workspaces/${workspaceId}/traces`);
  }

  async getTrace(workspaceId: string, traceId: string): Promise<Trace> {
    return this.request<Trace>(`/api/v1/workspaces/${workspaceId}/traces/${traceId}`);
  }

  async getMetricsRaw(): Promise<string> {
    const res = await fetch(`${BASE_URL}/metrics`);
    return res.text();
  }
}

export const api = new ApiClient();
