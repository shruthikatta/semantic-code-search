"use client";

import { useEffect, useState } from "react";
import { SearchBar } from "@/components/SearchBar";
import { ResultCard } from "@/components/ResultCard";
import { getStats, search, type SearchResponse } from "@/lib/api";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [k, setK] = useState(10);
  const [mode, setMode] = useState<"hybrid" | "bm25" | "vector">("hybrid");
  const [repo, setRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<SearchResponse | null>(null);
  const [repos, setRepos] = useState<string[]>([]);
  const [docCount, setDocCount] = useState<number | null>(null);

  useEffect(() => {
    getStats()
      .then((s) => {
        setRepos(s.repos ?? []);
        setDocCount(s.doc_count ?? 0);
      })
      .catch(() => undefined);
  }, []);

  async function onSubmit() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await search(query.trim(), k, mode, repo || undefined);
      setResp(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResp(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Semantic Code Search</h1>
        <p className="text-slate-400 mt-1">
          Hybrid BM25 + dense-vector retrieval over AST-aware Python chunks.
          {docCount !== null && (
            <>
              {" "}
              <span className="text-slate-500">
                · {docCount.toLocaleString()} chunks indexed
                {repos.length > 0 && <> across {repos.length} repo{repos.length === 1 ? "" : "s"}</>}
              </span>
            </>
          )}
        </p>
      </header>

      <SearchBar
        query={query}
        k={k}
        mode={mode}
        repo={repo}
        loading={loading}
        repos={repos}
        onChange={(n) => {
          if (n.query !== undefined) setQuery(n.query);
          if (n.k !== undefined) setK(n.k);
          if (n.mode !== undefined) setMode(n.mode);
          if (n.repo !== undefined) setRepo(n.repo);
        }}
        onSubmit={onSubmit}
      />

      {error && (
        <div className="mt-6 rounded-lg border border-red-700 bg-red-950/40 p-3 text-red-200 text-sm">
          {error}
        </div>
      )}

      {resp && (
        <section className="mt-8">
          <p className="text-sm text-slate-400 mb-4">
            {resp.hits.length} result{resp.hits.length === 1 ? "" : "s"} · mode={resp.mode} · {resp.took_ms}ms
          </p>
          <div className="flex flex-col gap-4">
            {resp.hits.map((h, i) => (
              <ResultCard key={`${h.repo}:${h.file_path}:${h.start_line}-${h.end_line}-${i}`} hit={h} rank={i + 1} />
            ))}
          </div>
          {resp.hits.length === 0 && (
            <div className="text-slate-400">No matches. Try different keywords or run /index first.</div>
          )}
        </section>
      )}

      {!resp && !error && (
        <section className="mt-10 text-slate-400 text-sm space-y-2">
          <p>Try queries like:</p>
          <ul className="list-disc list-inside space-y-1">
            <li>encoder decoder LSTM for anomaly detection</li>
            <li>multivariate time series forecasting on CloudWatch metrics</li>
            <li>automated failover between AWS regions</li>
            <li>update Route 53 DNS records when health check fails</li>
            <li>EventBridge rule triggering Lambda for traffic switch</li>
            <li>train a SageMaker model on streaming telemetry</li>
          </ul>
        </section>
      )}
    </main>
  );
}
