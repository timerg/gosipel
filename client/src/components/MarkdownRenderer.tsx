import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  h1: ({ children }) => <h1 className="mb-3 mt-4 text-2xl font-bold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-xl font-bold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 text-lg font-semibold">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-1 mt-3 text-base font-semibold">{children}</h4>,
  h5: ({ children }) => <h5 className="mb-1 mt-2 text-sm font-semibold">{children}</h5>,
  h6: ({ children }) => <h6 className="mb-1 mt-2 text-sm font-medium text-zinc-500">{children}</h6>,
  p:  ({ children }) => <p className="mb-3 leading-relaxed last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-4 border-zinc-300 pl-4 text-zinc-500 dark:border-zinc-600 dark:text-zinc-400">
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = className?.startsWith("language-");
    return isBlock ? (
      <code className="block w-full overflow-x-auto rounded-md bg-zinc-900 p-4 font-mono text-sm text-zinc-100 dark:bg-zinc-800" {...props}>
        {children}
      </code>
    ) : (
      <code className="rounded bg-zinc-200 px-1 py-0.5 font-mono text-sm dark:bg-zinc-700" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="mb-3 overflow-x-auto rounded-md">{children}</pre>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline hover:opacity-80">
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-zinc-200 dark:border-zinc-700" />,
};

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
