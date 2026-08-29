// Manual mock: react-markdown ships ESM-only and Jest can't parse it.
// Tests only need the text content, not real markdown rendering.
export default function ReactMarkdown({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
