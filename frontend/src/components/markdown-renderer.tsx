import React, { useState } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { Check, Copy } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

// ─── Streaming-safe markdown parser ──────────────────────────────────────────
// Splits content into text and fenced code block segments, tolerating
// unclosed/mid-stream blocks so the UI updates in real time.

type Part =
  | { type: "text"; content: string }
  | { type: "code"; language: string; content: string };

function parseMarkdown(raw: string): Part[] {
  const parts: Part[] = [];
  let remaining = raw;

  while (remaining.length > 0) {
    const start = remaining.indexOf("```");
    if (start === -1) {
      parts.push({ type: "text", content: remaining });
      break;
    }

    // Text before the fence
    if (start > 0) {
      parts.push({ type: "text", content: remaining.slice(0, start) });
    }

    const afterFence = remaining.slice(start + 3);
    const nlIdx = afterFence.indexOf("\n");

    if (nlIdx === -1) {
      // Still typing the language tag on same line — treat rest as code
      parts.push({ type: "code", language: afterFence.trim(), content: "" });
      break;
    }

    const language = afterFence.slice(0, nlIdx).trim();
    const body = afterFence.slice(nlIdx + 1);
    const closingIdx = body.indexOf("```");

    if (closingIdx === -1) {
      // Unclosed block — still streaming
      parts.push({ type: "code", language, content: body });
      remaining = "";
    } else {
      parts.push({ type: "code", language, content: body.slice(0, closingIdx) });
      remaining = body.slice(closingIdx + 3);
    }
  }

  return parts;
}

// ─── Language alias normalizer for Prism ─────────────────────────────────────

function normalizeLang(lang: string): string {
  const map: Record<string, string> = {
    js: "javascript",
    ts: "typescript",
    tsx: "tsx",
    jsx: "jsx",
    py: "python",
    sh: "bash",
    shell: "bash",
    zsh: "bash",
    yml: "yaml",
    dax: "sql",       // closest prism grammar
    sqlserver: "sql",
    md: "markdown",
  };
  return map[lang.toLowerCase()] ?? lang.toLowerCase();
}

// ─── Code Block ───────────────────────────────────────────────────────────────

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const lang = normalizeLang(language);
  const displayLang = language || "code";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable
    }
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-zinc-800 bg-[#0d1117] shadow-md text-xs font-mono">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-zinc-800">
        <div className="flex items-center gap-2">
          {/* Traffic-light dots */}
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-600" />
          <span className="ml-2 text-[10px] text-zinc-500 uppercase tracking-widest font-sans">
            {displayLang}
          </span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-200 transition-colors text-[10px] font-sans py-0.5 px-2 rounded hover:bg-zinc-700/50"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-green-400" />
              <span className="text-green-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Highlighted code via prism-react-renderer */}
      <Highlight
        theme={themes.oneDark}
        code={code.trimEnd()}
        language={lang as any}
      >
        {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={`${className} p-4 overflow-x-auto leading-relaxed text-[12px]`}
            style={{ ...style, background: "transparent", margin: 0 }}
          >
            {tokens.map((line, lineIdx) => (
              <div key={lineIdx} {...getLineProps({ line })}>
                {/* Line number */}
                <span className="select-none mr-4 text-zinc-600 text-[10px] inline-block w-5 text-right">
                  {lineIdx + 1}
                </span>
                {line.map((token, tokenIdx) => (
                  <span key={tokenIdx} {...getTokenProps({ token })} />
                ))}
              </div>
            ))}
          </pre>
        )}
      </Highlight>
    </div>
  );
}

// ─── Text renderer — handles bold, italic, inline code, headings ──────────────

function renderInline(text: string): React.ReactNode {
  // Split on inline code first
  const segments = text.split(/(`[^`\n]+`)/g);
  return segments.map((seg, i) => {
    if (seg.startsWith("`") && seg.endsWith("`")) {
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 mx-0.5 rounded bg-zinc-100 border border-zinc-200 text-orange-600 font-mono text-[11px]"
        >
          {seg.slice(1, -1)}
        </code>
      );
    }
    // Bold **text**
    const boldSplit = seg.split(/(\*\*[^*]+\*\*)/g);
    return (
      <React.Fragment key={i}>
        {boldSplit.map((b, bi) => {
          if (b.startsWith("**") && b.endsWith("**")) {
            return (
              <strong key={bi} className="font-semibold text-zinc-900">
                {b.slice(2, -2)}
              </strong>
            );
          }
          // Italic *text*
          const italicSplit = b.split(/(\*[^*]+\*)/g);
          return (
            <React.Fragment key={bi}>
              {italicSplit.map((it, ii) =>
                it.startsWith("*") && it.endsWith("*") ? (
                  <em key={ii} className="italic text-zinc-600">
                    {it.slice(1, -1)}
                  </em>
                ) : (
                  it
                )
              )}
            </React.Fragment>
          );
        })}
      </React.Fragment>
    );
  });
}

function TextPart({ text }: { text: string }) {
  if (!text.trim()) return null;

  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let ulItems: string[] = [];
  let olItems: { n: number; text: string }[] = [];

  const flushUl = (key: string) => {
    if (!ulItems.length) return;
    elements.push(
      <ul key={key} className="my-1.5 pl-5 space-y-0.5 list-disc text-zinc-700 text-sm">
        {ulItems.map((li, i) => (
          <li key={i}>{renderInline(li)}</li>
        ))}
      </ul>
    );
    ulItems = [];
  };

  const flushOl = (key: string) => {
    if (!olItems.length) return;
    elements.push(
      <ol key={key} className="my-1.5 pl-5 space-y-0.5 list-decimal text-zinc-700 text-sm">
        {olItems.map((li, i) => (
          <li key={i}>{renderInline(li.text)}</li>
        ))}
      </ol>
    );
    olItems = [];
  };

  lines.forEach((line, idx) => {
    const key = `line-${idx}`;

    // Headings
    const h3 = line.match(/^###\s+(.*)/);
    const h2 = line.match(/^##\s+(.*)/);
    const h1 = line.match(/^#\s+(.*)/);

    if (h1 || h2 || h3) {
      flushUl(key + "ul");
      flushOl(key + "ol");
      const txt = (h1 || h2 || h3)![1];
      const cls = h1
        ? "text-base font-bold text-zinc-900 mt-3 mb-1"
        : h2
        ? "text-sm font-bold text-zinc-900 mt-2.5 mb-1"
        : "text-sm font-semibold text-zinc-800 mt-2 mb-0.5";
      elements.push(
        <p key={key} className={cls}>
          {renderInline(txt)}
        </p>
      );
      return;
    }

    // Unordered list
    const ulMatch = line.match(/^[-*+]\s+(.*)/);
    if (ulMatch) {
      flushOl(key + "ol");
      ulItems.push(ulMatch[1]);
      return;
    }

    // Ordered list
    const olMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (olMatch) {
      flushUl(key + "ul");
      olItems.push({ n: parseInt(olMatch[1]), text: olMatch[2] });
      return;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      flushUl(key + "ul");
      flushOl(key + "ol");
      elements.push(<hr key={key} className="border-zinc-200 my-2" />);
      return;
    }

    // Normal line
    flushUl(key + "ul");
    flushOl(key + "ol");
    if (line.trim() === "") {
      elements.push(<div key={key} className="h-1.5" />);
    } else {
      elements.push(
        <p key={key} className="text-zinc-800 text-sm leading-relaxed">
          {renderInline(line)}
        </p>
      );
    }
  });

  flushUl("end-ul");
  flushOl("end-ol");

  return <div className="space-y-0.5">{elements}</div>;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;
  const parts = parseMarkdown(content);

  return (
    <div className="space-y-1">
      {parts.map((part, i) =>
        part.type === "code" ? (
          <CodeBlock key={i} language={part.language} code={part.content} />
        ) : (
          <TextPart key={i} text={part.content} />
        )
      )}
    </div>
  );
}
