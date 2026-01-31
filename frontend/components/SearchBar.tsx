"use client";

import { FormEvent } from "react";

interface Props {
  query: string;
  k: number;
  mode: "hybrid" | "bm25" | "vector";
  repo: string;
  onChange: (next: { query?: string; k?: number; mode?: Props["mode"]; repo?: string }) => void;
  onSubmit: () => void;
  loading: boolean;
  repos: string[];
}

export function SearchBar({ query, k, mode, repo, onChange, onSubmit, loading, repos }: Props) {
  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }

  return (
    <form onSubmit={submit} className="w-full">
      <div className="flex flex-col md:flex-row gap-2">
        <input
          type="text"
          autoFocus
          value={query}
          onChange={(e) => onChange({ query: e.target.value })}
          placeholder="Describe the code you're looking for..."
          className="flex-1 px-4 py-3 rounded-lg bg-slate-900 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={mode}
          onChange={(e) => onChange({ mode: e.target.value as Props["mode"] })}
          className="px-3 py-3 rounded-lg bg-slate-900 border border-slate-700"
          aria-label="Search mode"
        >
          <option value="hybrid">hybrid (BM25 + vector)</option>
          <option value="bm25">BM25 only</option>
          <option value="vector">vector only</option>
        </select>
        <select
          value={k}
          onChange={(e) => onChange({ k: Number(e.target.value) })}
          className="px-3 py-3 rounded-lg bg-slate-900 border border-slate-700"
          aria-label="Result count"
        >
          {[5, 10, 20, 50].map((n) => (
            <option key={n} value={n}>
              top {n}
            </option>
          ))}
        </select>
        <select
          value={repo}
          onChange={(e) => onChange({ repo: e.target.value })}
          className="px-3 py-3 rounded-lg bg-slate-900 border border-slate-700"
          aria-label="Repository filter"
        >
          <option value="">all repos</option>
          {repos.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-5 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 font-medium"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>
    </form>
  );
}
