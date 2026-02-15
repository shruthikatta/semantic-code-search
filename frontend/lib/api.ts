export type SymbolKind = "function" | "method" | "class" | "module";

export interface SearchHit {
  score: number;
  repo: string;
  file_path: string;
  symbol_kind: SymbolKind;
  qualified_name: string;
  signature: string;
  docstring: string;
  code: string;
  start_line: number;
  end_line: number;
}

export interface SearchResponse {
  query: string;
  k: number;
  mode: "hybrid" | "bm25" | "vector";
  hits: SearchHit[];
  took_ms: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function search(
  q: string,
  k = 10,
  mode: "hybrid" | "bm25" | "vector" = "hybrid",
  repo?: string,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, k: String(k), mode });
  if (repo) params.set("repo", repo);
  const r = await fetch(`${API_BASE}/search?${params.toString()}`, { cache: "no-store" });
  if (!r.ok) {
    const text = await r.text();
    const clipped = text.length > 800 ? `${text.slice(0, 800)}…` : text;
    throw new Error(`Search failed (${r.status}): ${clipped}`);
  }
  return (await r.json()) as SearchResponse;
}

export async function getStats(): Promise<{
  index: string;
  exists: boolean;
  doc_count?: number;
  repos?: string[];
}> {
  const r = await fetch(`${API_BASE}/index/stats`, { cache: "no-store" });
  if (!r.ok) {
    const text = await r.text();
    const clipped = text.length > 800 ? `${text.slice(0, 800)}…` : text;
    throw new Error(`Stats request failed (${r.status}): ${clipped}`);
  }
  return r.json();
}
