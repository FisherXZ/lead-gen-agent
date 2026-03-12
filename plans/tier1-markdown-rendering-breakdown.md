# Tier 1: Markdown Rendering — Detailed Technical Breakdown

**Author:** Engineer 1
**Date:** 2026-03-11
**Status:** PLAN (not yet implemented)

---

## 1. Packages to Install

```bash
npm i streamdown @streamdown/code @tailwindcss/typography
```

| Package | Purpose | Notes |
|---|---|---|
| `streamdown` | Streaming-aware markdown renderer built for Vercel AI SDK | Handles partial markdown mid-stream (incomplete tables, unclosed code blocks). Memoized LRU rendering. React component API. |
| `@streamdown/code` | Shiki-based code highlighting plugin for streamdown | Provides syntax highlighting for fenced code blocks. Shiki is bundled (no separate install). |
| `@tailwindcss/typography` | Prose typography classes for Tailwind | Provides `prose` classes that style raw HTML elements (headings, tables, lists, links, code, etc.) with sensible defaults. |

**Version note:** I was unable to verify exact latest version numbers from npm (tool access issue). The implementing engineer should run `npm view streamdown version`, `npm view @streamdown/code version`, and `npm view @tailwindcss/typography version` before installing, and pin to those versions. If `streamdown` does not exist on npm yet (it may still be in Vercel's private/canary channel), see **Section 8: Fallback Plan** below.

---

## 2. File-by-File Changes

### 2a. `frontend/package.json`

**Change:** Three new dependencies added via `npm install`. No manual edits needed.

### 2b. `frontend/src/app/globals.css`

**Current state:**
```css
@import "tailwindcss";

:root {
  --background: #f8fafc;
  --foreground: #0f172a;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

body {
  background: var(--background);
  color: var(--foreground);
}
```

**After:**
```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";

:root {
  --background: #f8fafc;
  --foreground: #0f172a;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

body {
  background: var(--background);
  color: var(--foreground);
}
```

**Key detail:** Tailwind v4 uses `@plugin` directive in CSS instead of a `tailwind.config.ts` plugins array. This project uses Tailwind v4 (confirmed by `"tailwindcss": "^4"` in devDependencies and `@tailwindcss/postcss` in postcss config). There is no `tailwind.config.ts` file — configuration is done in CSS.

### 2c. `frontend/src/components/chat/MarkdownMessage.tsx` (NEW FILE)

This is a thin wrapper that encapsulates all markdown rendering logic. It keeps `ChatMessage.tsx` clean and provides a single place to configure styling/plugins.

```tsx
"use client";

import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";

interface MarkdownMessageProps {
  content: string;
  isStreaming: boolean;
}

const plugins = { code };

const components = {
  table: ({ children, ...props }: React.ComponentProps<"table">) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-slate-200">
      <table {...props} className="min-w-full">
        {children}
      </table>
    </div>
  ),
  a: ({ children, ...props }: React.ComponentProps<"a">) => (
    <a {...props} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export default function MarkdownMessage({
  content,
  isStreaming,
}: MarkdownMessageProps) {
  if (!content || content.trim() === "") {
    return null;
  }

  return (
    <div className="prose prose-sm prose-slate max-w-none prose-headings:font-semibold prose-headings:text-slate-800 prose-p:leading-relaxed prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:rounded-lg prose-th:text-left prose-th:font-medium prose-td:py-1.5 prose-th:py-1.5">
      <Streamdown
        animated
        plugins={plugins}
        components={components}
        isAnimating={isStreaming}
      >
        {content}
      </Streamdown>
    </div>
  );
}
```

**Props explained:**
- `content: string` — The raw markdown text from the AI message part
- `isStreaming: boolean` — Whether the message is still being streamed. Streamdown uses this to know whether to apply its `remend` strategy (auto-closing incomplete markdown elements) and memoized incremental rendering

**Prose class breakdown:**
- `prose prose-sm` — Base typography with small size (14px body), matching our existing `text-sm`
- `prose-slate` — Slate color scheme matching our design system
- `max-w-none` — Disable prose's default max-width (the parent container handles width)
- `prose-headings:font-semibold prose-headings:text-slate-800` — Heading style overrides
- `prose-p:leading-relaxed` — Match existing `leading-relaxed` on text
- `prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline` — Link styling
- `prose-code:*` — Inline code: subtle gray background, remove backtick pseudo-elements
- `prose-pre:bg-slate-900 prose-pre:rounded-lg` — Code blocks: dark background
- `prose-th:text-left prose-th:font-medium prose-td:py-1.5 prose-th:py-1.5` — Table cell padding

**Component overrides:**
- `table` — Wrapped in `overflow-x-auto` div for horizontal scrolling on wide tables
- `a` — All links open in new tab (`target="_blank"`) with `rel="noopener noreferrer"` for security

**Plugin configuration:**
- `plugins` and `components` are declared as module-level constants (outside the component) to avoid unnecessary re-renders. They are referentially stable.

### 2d. `frontend/src/components/chat/ChatMessage.tsx` (MODIFIED)

**Current state (lines 1-54):** See full file above.

**After:**
```tsx
"use client";

import type { UIMessage } from "ai";
import ToolPart from "./ToolPart";
import MarkdownMessage from "./MarkdownMessage";

interface ChatMessageProps {
  message: UIMessage;
  isStreaming?: boolean;
}

export default function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-slate-200 text-slate-800"
        }`}
      >
        <div className="space-y-2">
          {message.parts.map((part, i) => {
            if (part.type === "text") {
              if (isUser) {
                // User messages: plain text (no markdown rendering)
                return (
                  <div
                    key={i}
                    className="whitespace-pre-wrap text-sm leading-relaxed"
                  >
                    {part.text}
                  </div>
                );
              }
              // Assistant messages: markdown rendering
              return (
                <MarkdownMessage
                  key={i}
                  content={part.text}
                  isStreaming={isStreaming}
                />
              );
            }
            if (part.type === "dynamic-tool") {
              return (
                <ToolPart
                  key={part.toolCallId || i}
                  toolInvocation={{
                    toolCallId: part.toolCallId,
                    toolName: part.toolName,
                    state: part.state === "output-available" ? "result" : "call",
                    input: part.input as Record<string, unknown> | undefined,
                    output: "output" in part ? (part.output as unknown) : undefined,
                  }}
                />
              );
            }
            return null;
          })}
        </div>
      </div>
    </div>
  );
}
```

**Changes from current:**
1. **New import:** `MarkdownMessage` from `./MarkdownMessage`
2. **New prop:** `isStreaming?: boolean` (optional, defaults to `false`)
3. **Text part rendering:** Split into two paths:
   - **User messages:** Keep current plain text rendering (users don't write markdown)
   - **Assistant messages:** Use `<MarkdownMessage>` component
4. **Tool part rendering:** UNCHANGED — this is Engineer 2's territory

### 2e. `frontend/src/components/chat/ChatInterface.tsx` (MODIFIED)

**Only change:** Pass `isStreaming` prop to `ChatMessage` for the last assistant message.

**Current (line 255-257):**
```tsx
{messages.map((m) => (
  <ChatMessage key={m.id} message={m} />
))}
```

**After:**
```tsx
{messages.map((m, idx) => (
  <ChatMessage
    key={m.id}
    message={m}
    isStreaming={
      status === "streaming" &&
      m.role === "assistant" &&
      idx === messages.length - 1
    }
  />
))}
```

**Why:** The `isStreaming` prop should only be `true` for the last assistant message while the chat status is `"streaming"`. Past messages are never streaming. The `status` variable is already available on line 55: `const isLoading = status === "submitted" || status === "streaming";`

---

## 3. How Streamdown Handles Streaming

Streamdown is purpose-built for streaming AI responses. Key behaviors:

1. **`remend` strategy:** When `isAnimating={true}`, Streamdown auto-closes incomplete markdown syntax. For example, if the stream stops mid-table (`| col1 | col2\n| val1 |`), it synthesizes closing markup so the table renders correctly, then re-renders with the real content as more tokens arrive.

2. **Memoized LRU rendering:** Streamdown caches parsed AST nodes. When new tokens append to the stream, only the new/changed nodes are re-parsed and re-rendered. This avoids the O(n^2) problem where naive `react-markdown` usage re-parses the entire message on every token.

3. **`animated` prop:** Enables smooth token-by-token appearance animation (CSS-based). When `isAnimating` becomes `false` (streaming complete), the full content displays statically.

4. **GFM built-in:** GitHub Flavored Markdown (tables, strikethrough, task lists, autolinks) is supported out of the box.

---

## 4. Edge Cases

### 4a. Empty text parts
`MarkdownMessage` returns `null` when `content` is falsy or whitespace-only. This prevents rendering empty prose containers.

### 4b. Streaming partial markdown
Handled by Streamdown's `remend` + memoized rendering (see Section 3). No special handling needed from our side.

### 4c. Very long messages
- `prose` class has a built-in `max-width` of `65ch` — we override this with `max-w-none` because the parent `.max-w-[85%]` bubble already constrains width
- Code blocks: `prose-pre` will overflow horizontally within the bubble. The `overflow-x-auto` on the prose container handles this. Streamdown/Shiki code blocks render inside `<pre>` which respects this.

### 4d. Tables wider than the chat container
The custom `table` component override wraps every table in `<div className="overflow-x-auto">` with a subtle border. This creates a horizontally scrollable region for wide tables while the rest of the message stays fixed.

### 4e. User messages
User messages are deliberately NOT rendered as markdown. Users type plain text, and rendering it as markdown would cause surprising formatting (e.g., `*asterisks*` becoming italic). The `isUser` check in `ChatMessage.tsx` preserves the current plain-text rendering for user messages.

### 4f. Prose styles bleeding into tool cards
Tool parts are rendered as siblings to text parts inside `<div className="space-y-2">`. The `prose` class is scoped to the `<div>` wrapper inside `MarkdownMessage`, so it does NOT affect `ToolPart` children. Prose styles only cascade to child elements, not siblings.

### 4g. User message prose conflict
User messages have `bg-blue-600 text-white`. Since we only apply `MarkdownMessage` (and thus `prose`) to assistant messages, there is no conflict. The `prose-slate` color scheme will not apply to user bubbles.

---

## 5. Integration Points with Engineer 2

### 5a. Shared file: `ChatMessage.tsx`

Both engineers modify this file. Here is the exact boundary:

**Engineer 1 (me) changes:**
- Add `import MarkdownMessage from "./MarkdownMessage";`
- Add `isStreaming?: boolean` to the `ChatMessageProps` interface
- Replace the text part `<div>` with a conditional: user messages stay as plain `<div>`, assistant messages use `<MarkdownMessage>`
- The `if (part.type === "text")` block (lines 24-33) is mine

**Engineer 2 changes:**
- The `if (part.type === "dynamic-tool")` block (lines 34-47) is theirs
- They may wrap the ToolPart in their new `CollapsibleToolCard`
- They should NOT touch the text rendering path

**Conflict risk: LOW.** The two changes are in separate `if` branches within the `.map()` callback. As long as Engineer 2 does not restructure the overall `.map()` logic, there will be no merge conflict.

### 5b. Shared file: `ChatInterface.tsx`

**Engineer 1 (me) changes:**
- Modify the `<ChatMessage>` call to pass `isStreaming` prop (lines 255-257)

**Engineer 2:** Should not need to touch `ChatInterface.tsx`. If they do, it would be for different lines. Low conflict risk.

### 5c. CSS / globals.css

**Engineer 1 (me):** Adds `@plugin "@tailwindcss/typography";` to `globals.css`

**Engineer 2:** May add CSS for collapse animations. These would be additive, not conflicting.

### 5d. Recommendation
To avoid merge conflicts, I suggest Engineer 1 completes and merges first (fewer files touched, simpler change), then Engineer 2 builds on top.

---

## 6. Risks and Open Questions

### 6a. CRITICAL: Streamdown availability
`streamdown` is a Vercel library referenced in their AI SDK documentation and used internally. **I was unable to verify it exists on the public npm registry** (tool access was blocked during planning). The implementing engineer MUST run `npm view streamdown` before starting.

**If streamdown is NOT available on npm**, use the fallback plan in Section 8.

### 6b. Streamdown API uncertainty
The exact prop names (`animated`, `isAnimating`, `plugins`, `components`) are based on the plan document and Vercel's documented patterns. The implementing engineer should check the actual package exports after installing. Key things to verify:
- Is the main export `Streamdown` or `StreamdownMarkdown` or something else?
- Is the plugin passed as `plugins={{ code }}` or via a `plugins={[code()]}` array?
- Does it accept a `components` prop (react-markdown style) or use a different override mechanism?
- Does it require any CSS import (e.g., `import "streamdown/styles.css"`)?

### 6c. Bundle size
Shiki (via `@streamdown/code`) bundles grammar definitions for all languages. This can add 2-5MB to the client bundle. Mitigation options:
- Streamdown may lazy-load grammars (verify after install)
- We can configure Shiki to only include languages we care about (python, sql, json, bash, typescript)
- If bundle size is unacceptable, we can drop `@streamdown/code` and use a lighter highlighter or no highlighting at all

### 6d. Tailwind v4 typography plugin compatibility
`@tailwindcss/typography` has been updated for Tailwind v4. The `@plugin` directive is the v4 way to register plugins. However, if the installed version does not yet support v4's `@plugin` syntax, the fallback is to use a CSS import:
```css
@import "@tailwindcss/typography";
```

### 6e. Prose colors in user bubble
Verified: not a risk. User messages use plain `<div>` rendering, not `MarkdownMessage`. No prose classes are applied to user messages.

### 6f. `next.config.ts` changes
Shiki uses WASM under the hood. If Next.js bundling fails with Shiki/WASM errors, we may need to add to `next.config.ts`:
```ts
const nextConfig: NextConfig = {
  webpack: (config) => {
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    return config;
  },
};
```
This should only be added if needed (try without it first).

---

## 7. Testing Checklist

After implementation, verify:

- [ ] Plain text assistant messages render without errors
- [ ] **Bold**, *italic*, `inline code` render correctly
- [ ] Headings (## H2, ### H3) render with correct sizing
- [ ] Bulleted and numbered lists render correctly
- [ ] Fenced code blocks render with syntax highlighting
- [ ] GFM tables render with proper alignment and horizontal scroll on overflow
- [ ] Links open in new tab
- [ ] User messages still render as plain text (no markdown interpretation)
- [ ] Streaming messages render incrementally without flicker
- [ ] Streaming partial tables/code blocks don't break layout
- [ ] Past (non-streaming) messages render correctly on page load
- [ ] Tool cards (EPC results, guidance, etc.) are unaffected by prose styles
- [ ] No console errors or hydration mismatches
- [ ] Bundle size increase is reasonable (check with `next build`)

---

## 8. Fallback Plan: react-markdown

If `streamdown` is not available on public npm, fall back to `react-markdown` + plugins:

```bash
npm i react-markdown remark-gfm rehype-highlight @tailwindcss/typography
```

The `MarkdownMessage.tsx` would then be:

```tsx
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { memo } from "react";

interface MarkdownMessageProps {
  content: string;
  isStreaming: boolean;
}

const MemoizedMarkdown = memo(function MemoizedMarkdown({
  content,
}: {
  content: string;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        table: ({ children, ...props }) => (
          <div className="overflow-x-auto my-2 rounded-lg border border-slate-200">
            <table {...props} className="min-w-full">
              {children}
            </table>
          </div>
        ),
        a: ({ children, ...props }) => (
          <a {...props} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

export default function MarkdownMessage({
  content,
  isStreaming,
}: MarkdownMessageProps) {
  if (!content || content.trim() === "") {
    return null;
  }

  return (
    <div className="prose prose-sm prose-slate max-w-none prose-headings:font-semibold prose-headings:text-slate-800 prose-p:leading-relaxed prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:rounded-lg prose-th:text-left prose-th:font-medium prose-td:py-1.5 prose-th:py-1.5">
      <MemoizedMarkdown content={content} />
    </div>
  );
}
```

**Tradeoffs vs. streamdown:**
- No built-in streaming optimization (every token re-parses entire content)
- Mitigation: `React.memo` prevents re-render if content hasn't changed, but during streaming each token IS a change. For long messages this causes O(n^2) parsing.
- Further mitigation: Split content by paragraphs (`\n\n`) and memo each paragraph separately (the approach used by Vercel's AI chatbot template before streamdown).
- `rehype-highlight` is lighter than Shiki (~200KB vs 2-5MB) but supports fewer languages and themes.
- No auto-closing of incomplete markdown during streaming (tables may flash broken during stream).

**If using the fallback, also install highlight.js CSS:**
Add to `globals.css`:
```css
@import "highlight.js/styles/github-dark.min.css";
```

---

## 9. Summary of All Files Touched

| File | Action | Owner |
|---|---|---|
| `frontend/package.json` | New deps added via npm | Engineer 1 |
| `frontend/src/app/globals.css` | Add `@plugin "@tailwindcss/typography"` | Engineer 1 |
| `frontend/src/components/chat/MarkdownMessage.tsx` | **NEW** — markdown wrapper component | Engineer 1 |
| `frontend/src/components/chat/ChatMessage.tsx` | Add `isStreaming` prop, conditional markdown rendering for assistant messages | Engineer 1 (text branch) / Engineer 2 (tool branch) |
| `frontend/src/components/chat/ChatInterface.tsx` | Pass `isStreaming` to ChatMessage | Engineer 1 |
| `frontend/next.config.ts` | Possibly add WASM config (only if Shiki fails) | Engineer 1 |
