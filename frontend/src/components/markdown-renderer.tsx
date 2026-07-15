import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  // Split content by code blocks: ```lang\ncode\n```
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-3">
      {parts.map((part, index) => {
        if (part.startsWith("```")) {
          // Extract language and code
          const match = part.match(/```(\w*)\n([\s\S]*?)```/);
          const lang = match ? match[1] : "";
          const code = match ? match[2].trim() : part.slice(3, -3).trim();

          return (
            <CodeBlock key={index} language={lang} code={code} />
          );
        } else {
          return <TextPart key={index} text={part} />;
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
        let cls = "text-amber-400"; // numbers
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = "text-sky-400 font-medium"; // JSON key
          } else {
            cls = "text-emerald-400"; // string values
          }
        } else if (/true|false/.test(match)) {
          cls = "text-orange-400 font-semibold";
        } else if (/null/.test(match)) {
          cls = "text-zinc-500";
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
    result = result.replace(/(".*?"|'.*?')/g, '<span class="text-emerald-400">$1</span>');

    // 2. Highlight keywords (case-insensitive boundary match)
    const regex = new RegExp(`\\b(${keywords.join("|")})\\b`, "gi");
    result = result.replace(
      regex,
      (match) => `<span class="text-sky-400 font-medium uppercase">${match}</span>`
    );

    // 3. Highlight comments: -- ... or // ...
    result = result.replace(
      /(--.*?\n|\/\/.*?\n)/g,
      '<span class="text-zinc-500 italic">$1</span>'
    );

    return result;
  }

  // Generic highlighting for code blocks (e.g. JS, TS, Python)
  // Let's highlight strings and basic control keywords
  const genericKeywords = [
    "import", "from", "as", "class", "def", "function", "const", "let", "var",
    "if", "else", "for", "while", "return", "async", "await", "try", "except", "catch"
  ];
  let genericResult = escaped;

  // strings
  genericResult = genericResult.replace(/(".*?"|'.*?'|`.*?`)/g, '<span class="text-emerald-400">$1</span>');

  // keywords
  const regexGen = new RegExp(`\\b(${genericKeywords.join("|")})\\b`, "g");
  genericResult = genericResult.replace(
    regexGen,
    (match) => `<span class="text-orange-400 font-medium">${match}</span>`
  );

  return genericResult;
}
