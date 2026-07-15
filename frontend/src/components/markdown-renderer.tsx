import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  // Robust streaming markdown parser to extract code blocks (even when incomplete/unclosed)
  const parts: { type: "text" | "code"; content: string; language?: string }[] = [];
  let remaining = content;

  while (remaining.length > 0) {
    const codeStartIdx = remaining.indexOf("```");
    if (codeStartIdx === -1) {
      parts.push({ type: "text", content: remaining });
      break;
    }

    if (codeStartIdx > 0) {
      parts.push({ type: "text", content: remaining.slice(0, codeStartIdx) });
    }

    const afterStart = remaining.slice(codeStartIdx + 3);
    const nextLineBreak = afterStart.indexOf("\n");
    let language = "";
    let codeContent = "";

    if (nextLineBreak !== -1) {
      language = afterStart.slice(0, nextLineBreak).trim();
      const codeAndRest = afterStart.slice(nextLineBreak + 1);
      const nextTripleBacktick = codeAndRest.indexOf("```");
      if (nextTripleBacktick !== -1) {
        codeContent = codeAndRest.slice(0, nextTripleBacktick);
        remaining = codeAndRest.slice(nextTripleBacktick + 3);
      } else {
        // Unclosed code block (still streaming!)
        codeContent = codeAndRest;
        remaining = "";
      }
    } else {
      // Still typing language name
      language = afterStart.trim();
      codeContent = "";
      remaining = "";
    }

    parts.push({ type: "code", content: codeContent, language });
  }

  return (
    <div className="space-y-3">
      {/* Self-contained styling to prevent Tailwind purging dynamic class colors */}
      <style dangerouslySetInnerHTML={{ __html: `
        .syntax-keyword { color: #38bdf8 !important; font-weight: 500; text-transform: uppercase; }
        .syntax-string { color: #34d399 !important; }
        .syntax-number { color: #fbbf24 !important; }
        .syntax-comment { color: #71717a !important; font-style: italic; }
        .syntax-generic-keyword { color: #fb923c !important; font-weight: 500; }
        .syntax-json-key { color: #38bdf8 !important; font-weight: 500; }
        .syntax-json-bool { color: #fb923c !important; font-weight: 600; }
        .syntax-json-null { color: #71717a !important; }
      `}} />
      {parts.map((part, index) => {
        if (part.type === "code") {
          return (
            <CodeBlock key={index} language={part.language || ""} code={part.content} />
          );
        } else {
          return <TextPart key={index} text={part.content} />;
        }
      })}
    </div>
  );
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy code: ", err);
    }
  };

  const highlightedHtml = highlightCode(code, language);

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-zinc-200 bg-zinc-950 text-zinc-100 shadow-sm font-mono text-xs">
      {/* Code Header */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-900 border-b border-zinc-800 text-[10px] text-zinc-400 font-sans uppercase tracking-wider">
        <span>{language || "code"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-zinc-200 transition-colors py-0.5 px-1.5 rounded hover:bg-zinc-800"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-green-500" />
              <span className="text-green-500">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      {/* Code Area */}
      <pre className="p-4 overflow-x-auto whitespace-pre leading-relaxed">
        <code dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
      </pre>
    </div>
  );
}

function TextPart({ text }: { text: string }) {
  if (!text) return null;

  // Split by inline code: `code`
  const parts = text.split(/(`[^`]+`)/g);

  return (
    <p className="whitespace-pre-wrap text-zinc-800 leading-relaxed font-sans text-sm">
      {parts.map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code
              key={index}
              className="px-1.5 py-0.5 mx-0.5 rounded bg-zinc-100 border border-zinc-200 text-orange-600 font-mono text-xs"
            >
              {part.slice(1, -1)}
            </code>
          );
        }

        // Handle bold: **text**
        const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
        return (
          <span key={index}>
            {boldParts.map((bp, bpIdx) => {
              if (bp.startsWith("**") && bp.endsWith("**")) {
                return (
                  <strong key={bpIdx} className="font-semibold text-zinc-950">
                    {bp.slice(2, -2)}
                  </strong>
                );
              }
              return bp;
            })}
          </span>
        );
      })}
    </p>
  );
}

function highlightCode(code: string, language: string): string {
  const lang = language.toLowerCase();

  const escapeHtml = (str: string) =>
    str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  const escaped = escapeHtml(code);

  if (lang === "json") {
    // Basic JSON syntax highlighting
    return escaped.replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      (match) => {
        let cls = "syntax-number"; // numbers
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = "syntax-json-key"; // JSON key
          } else {
            cls = "syntax-string"; // string values
          }
        } else if (/true|false/.test(match)) {
          cls = "syntax-json-bool";
        } else if (/null/.test(match)) {
          cls = "syntax-json-null";
        }
        return `<span class="${cls}">${match}</span>`;
      }
    );
  }

  if (lang === "dax" || lang === "sql" || lang === "sqlserver") {
    // Keywords for DAX & SQL
    const keywords = [
      "EVALUATE", "DEFINE", "MEASURE", "VAR", "RETURN", "CALCULATE", "FILTER", "ALL",
      "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "SUM", "AVERAGE", "COUNT",
      "MIN", "MAX", "CALCULATETABLE", "ADDCOLUMNS", "SUMMARIZE", "ROW", "VALUES",
      "KEEPFILTERS", "USERELATIONSHIP", "CROSSFILTER", "RELATED", "RELATEDTABLE"
    ];

    let result = escaped;

    // 1. Highlight strings: "..." or '...'
    result = result.replace(/(".*?"|'.*?')/g, '<span class="syntax-string">$1</span>');

    // 2. Highlight keywords (case-insensitive boundary match)
    const regex = new RegExp(`\\b(${keywords.join("|")})\\b`, "gi");
    result = result.replace(
      regex,
      (match) => `<span class="syntax-keyword">${match}</span>`
    );

    // 3. Highlight comments: -- ... or // ...
    result = result.replace(
      /(--.*?\n|\/\/.*?\n)/g,
      '<span class="syntax-comment">$1</span>'
    );

    return result;
  }

  // Generic highlighting for code blocks (e.g. JS, TS, Python)
  const genericKeywords = [
    "import", "from", "as", "class", "def", "function", "const", "let", "var",
    "if", "else", "for", "while", "return", "async", "await", "try", "except", "catch"
  ];
  let genericResult = escaped;

  // strings
  genericResult = genericResult.replace(/(".*?"|'.*?'|`.*?`)/g, '<span class="syntax-string">$1</span>');

  // keywords
  const regexGen = new RegExp(`\\b(${genericKeywords.join("|")})\\b`, "g");
  genericResult = genericResult.replace(
    regexGen,
    (match) => `<span class="syntax-generic-keyword">${match}</span>`
  );

  return genericResult;
}
