# IntelligenceOS Security, Data Protection & AI Safety Policy

## Document Control
- Policy Ref: SEC-SAF-2026-V1
- Security Level: Confidential / Enterprise Standard
- Compliance: SOC 2 Type II, ISO/IEC 27001, GDPR, HIPAA Ready

## 1. Data Protection & Tenant Boundary
IntelligenceOS is engineered around zero-trust multi-tenancy:
1. **Namespace Isolation in Vector Storage**:
   Every vector point indexed in Qdrant is partitioned using a strict payload schema containing `workspace_id`. All retrieval filters unconditionally inject a must-match clause on `workspace_id`. Cross-tenant search execution is rejected at the query construction layer.
2. **Encryption at Rest**:
   All metadata stored in PostgreSQL is encrypted using AES-256. Raw file uploads stored in Supabase Storage buckets utilize server-side AES-256 encryption.
3. **Encryption in Transit**:
   All external and internal network communications require TLS 1.3 encryption. Unencrypted HTTP endpoints are disallowed in production environments.

## 2. Authentication & Session Management
- **JWT Authentication**: User sessions are authenticated using JSON Web Tokens (JWT) signed with secure algorithmic secrets.
- **Role-Based Access Control (RBAC)**:
  - **Owner**: Full access, billing management, workspace deletion, API key configuration.
  - **Admin**: Document ingestion, member invitations, evaluation run trigger, model parameter adjustments.
  - **Member**: Chat querying, read access to knowledge documents and evaluation results.
  - **Viewer**: Read-only access to published conversation logs.

## 3. AI Safety, Guardrails & Prompt Injection Defense
To safeguard against prompt injection, data exfiltration, and hallucinations, IntelligenceOS enforces a tri-fold safety defense:
1. **Input Sanitization & Injection Detection**:
   Incoming user prompts are analyzed for system prompt override vectors (e.g. "Ignore previous instructions", "SYSTEM PROMPT OVERRIDE", Markdown jailbreak delimiters). Identified attack strings trigger safe query deflection.
2. **Strict RAG Grounding Constraint**:
   The synthesis engine is instructed to rely solely on the retrieved workspace context. If an answer cannot be grounded directly from the provided source chunks, the system must reply:
   *"Based on the provided workspace documents, this information is not available."* Hallucinatory extrapolations are strictly penalized during automated evaluation sweeps.
3. **PII Redaction Guardrails**:
   Generated model responses are scanned for sensitive personally identifiable information (Social Security numbers, credit card numbers, secret API keys) before being streamed to client browsers.

## 4. Audit Logging & Tracing Observability
All agent tool executions, ingestion operations, and LLM inference calls emit OpenTelemetry-compliant trace spans containing timestamps, latency metrics, token consumption, and status flags. Audit logs are preserved for 365 days in tamper-evident storage.
