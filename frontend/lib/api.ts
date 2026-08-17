export const API =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ContractMeta {
  parties: string[];
  effective_date?: string | null;
  term?: string | null;
  renewal_terms?: string | null;
  termination_terms?: string | null;
  governing_law?: string | null;
  total_value?: string | null;
}

export interface Contract {
  id: string;
  filename: string;
  status: string;
  progress?: string | null;
  created_at?: string | null;
  meta?: ContractMeta | null;
  summary?: string | null;
  num_clauses: number;
  num_obligations: number;
  num_risks: number;
  num_nonstandard: number;
}

export interface Obligation {
  id: string;
  contract_id: string;
  description: string;
  obligated_party?: string | null;
  obligation_type: string;
  due_date?: string | null;
  trigger?: string | null;
  source_clause_id: string;
  source_quote?: string | null;
}

export type ReviewStatus = "pending" | "approved" | "dismissed";

export interface Risk {
  id: string;
  contract_id: string;
  category: string;
  severity: string;
  title: string;
  rationale?: string | null;
  source_clause_id: string;
  source_quote?: string | null;
  flagged_by: "llm" | "rule";
  review_status: ReviewStatus;
  reviewer_note?: string | null;
}

// --- Human-in-the-loop risk review (LangGraph) ---
export interface RiskReviewStart {
  contract_id: string;
  thread_id: string;
  status: "awaiting_review" | "complete";
  pending: Risk[];
  message?: string | null;
}
export interface RiskDecision {
  risk_id: string;
  action: "approve" | "dismiss" | "edit";
  severity?: "high" | "medium" | "low";
  note?: string | null;
}
export interface RiskReviewResult {
  contract_id: string;
  status: "complete";
  approved: number;
  dismissed: number;
  edited: number;
  summary: string;
}

// --- Multi-contract comparison agent (LangGraph) ---
export interface CompareRow {
  dimension: string;
  findings: Record<string, string>;
  assessment?: string | null;
}
export interface CompareCitation {
  contract_id: string;
  contract_name?: string | null;
  clause_id: string;
  section?: string | null;
  quote?: string | null;
}
export interface CompareResponse {
  contract_ids: string[];
  contract_names: Record<string, string>;
  dimensions: CompareRow[];
  verdict: string;
  citations: CompareCitation[];
}

// --- Obligation calendar agent (LangGraph) ---
export type CalendarBucket =
  | "overdue" | "next_30_days" | "next_90_days" | "later" | "recurring" | "unscheduled";
export interface CalendarEvent {
  obligation_id: string;
  contract_id: string;
  title: string;
  obligated_party?: string | null;
  obligation_type: string;
  raw_due?: string | null;
  resolved_date?: string | null;
  bucket: CalendarBucket;
  urgency: "high" | "medium" | "low";
  note?: string | null;
  source_clause_id: string;
}
export interface CalendarResponse {
  contract_id: string;
  reference_date: string;
  events: CalendarEvent[];
  summary: string;
}

export interface ClauseSummary {
  clause_id: string;
  section?: string | null;
  heading?: string | null;
  clause_type: string;
  page?: number | null;
  preview: string;
  is_scanned: boolean;
  nonstandard: boolean;
  nonstandard_similarity?: number | null;
}

export interface Clause {
  clause_id: string;
  contract_id: string;
  section?: string | null;
  heading?: string | null;
  clause_type: string;
  page?: number | null;
  text: string;
  is_scanned: boolean;
  nonstandard: boolean;
  nonstandard_similarity?: number | null;
  nonstandard_explanation?: string | null;
  standard_title?: string | null;
  standard_text?: string | null;
}

export interface Citation {
  clause_id: string;
  section?: string | null;
  heading?: string | null;
  page?: number | null;
  quote?: string | null;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  confidence: "high" | "low";
  faithfulness_note?: string | null;
  mode: "agent" | "rag";
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = String(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listContracts: () =>
    fetch(`${API}/contracts`, { cache: "no-store" }).then((r) => j<Contract[]>(r)),
  getContract: (id: string) =>
    fetch(`${API}/contracts/${id}`, { cache: "no-store" }).then((r) => j<Contract>(r)),
  ingest: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${API}/ingest`, { method: "POST", body: fd }).then((r) =>
      j<{ contract_id: string; status: string }>(r)
    );
  },
  obligations: (id: string) =>
    fetch(`${API}/contracts/${id}/obligations`, { cache: "no-store" }).then((r) =>
      j<Obligation[]>(r)
    ),
  risks: (id: string) =>
    fetch(`${API}/contracts/${id}/risks`, { cache: "no-store" }).then((r) => j<Risk[]>(r)),
  clauses: (id: string) =>
    fetch(`${API}/contracts/${id}/clauses`, { cache: "no-store" }).then((r) =>
      j<ClauseSummary[]>(r)
    ),
  clause: (clauseId: string) =>
    fetch(`${API}/clauses/${clauseId}`, { cache: "no-store" }).then((r) => j<Clause>(r)),
  ask: (contract_id: string, question: string, use_agent: boolean) =>
    fetch(`${API}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_id, question, use_agent }),
    }).then((r) => j<AskResponse>(r)),

  // --- LangGraph agents ---
  risks2: (id: string, status?: string) =>
    fetch(`${API}/contracts/${id}/risks${status ? `?status=${status}` : ""}`, {
      cache: "no-store",
    }).then((r) => j<Risk[]>(r)),
  riskReviewStart: (id: string) =>
    fetch(`${API}/contracts/${id}/risk-review/start`, { method: "POST" }).then((r) =>
      j<RiskReviewStart>(r)
    ),
  riskReviewResume: (id: string, thread_id: string, decisions: RiskDecision[]) =>
    fetch(`${API}/contracts/${id}/risk-review/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_id: id, thread_id, decisions }),
    }).then((r) => j<RiskReviewResult>(r)),
  compare: (contract_ids: string[], question: string) =>
    fetch(`${API}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_ids, question }),
    }).then((r) => j<CompareResponse>(r)),
  calendar: (id: string, reference_date?: string) =>
    fetch(`${API}/contracts/${id}/calendar${reference_date ? `?reference_date=${reference_date}` : ""}`, {
      cache: "no-store",
    }).then((r) => j<CalendarResponse>(r)),
};
