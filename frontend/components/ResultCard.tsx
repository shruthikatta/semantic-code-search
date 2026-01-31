"use client";

import { useEffect, useState } from "react";
import type { SearchHit } from "@/lib/api";

interface Props {
  hit: SearchHit;
  rank: number;
}

const KIND_COLORS: Record<string, string> = {
  function: "bg-emerald-700/40 text-emerald-200",
  method: "bg-sky-700/40 text-sky-200",
  class: "bg-fuchsia-700/40 text-fuchsia-200",
  module: "bg-amber-700/40 text-amber-200",
};

export function ResultCard({ hit, rank }: Props) {
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { codeToHtml } = await import("shiki");
      try {
        const out = await codeToHtml(hit.code, {
          lang: "python",
          theme: "github-dark",
        });
        if (!cancelled) setHtml(out);
      } catch {
        if (!cancelled) setHtml(`<pre class="shiki"><code>${escapeHtml(hit.code)}</code></pre>`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hit.code]);

  const kindClass = KIND_COLORS[hit.symbol_kind] ?? "bg-slate-700/40 text-slate-200";
  const vscodeLink = `vscode://file${hit.file_path.startsWith("/") ? "" : "/"}${hit.file_path}:${hit.start_line}`;

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-lg">
      <header className="flex flex-wrap items-center gap-2 mb-2 text-sm">
        <span className="text-slate-500">#{rank}</span>
        <span className={`px-2 py-0.5 rounded ${kindClass}`}>{hit.symbol_kind}</span>
        <span className="font-mono font-semibold text-slate-100 truncate">{hit.qualified_name}</span>
        <span className="text-slate-500">·</span>
        <span className="font-mono text-slate-400 truncate">
          {hit.repo}/{hit.file_path}:{hit.start_line}-{hit.end_line}
        </span>
        <span className="ml-auto text-xs text-slate-400">score {hit.score.toFixed(4)}</span>
      </header>
      {hit.signature && (
        <pre className="font-mono text-xs text-indigo-300 mb-2 whitespace-pre-wrap">{hit.signature}</pre>
      )}
      {hit.docstring && (
        <p className="text-sm text-slate-300 mb-3 italic line-clamp-3">{hit.docstring}</p>
      )}
      <div className="rounded-lg overflow-hidden" dangerouslySetInnerHTML={{ __html: html || "<pre class=\"shiki\"><code>...</code></pre>" }} />
      <footer className="mt-2 flex gap-3 text-xs text-slate-400">
        <a href={vscodeLink} className="underline hover:text-indigo-300">
          Open in VS Code
        </a>
      </footer>
    </article>
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
