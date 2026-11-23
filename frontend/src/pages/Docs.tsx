import { useState, type ComponentPropsWithoutRef } from 'react';
import { Link, Navigate, NavLink, useParams } from 'react-router-dom';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BookOpen, Check, Copy, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import { useDocs } from '../hooks/useDocs';
import { PageTitle } from '@/components/common/PageTitle';
import { useBreadcrumbOverride } from '@/contexts/BreadcrumbContext';
import { docsHref } from '../utils/docsHref';

function DocLink({ href = '', children, node: _node, ...rest }: ComponentPropsWithoutRef<'a'> & { node?: unknown }) {
  const internal = docsHref(href);
  if (internal) return <Link to={internal}>{children}</Link>;
  const external = /^https?:/i.test(href);
  return (
    <a href={href} {...rest} {...(external && { target: '_blank', rel: 'noopener noreferrer' })}>
      {children}
    </a>
  );
}

function CodeBlock({ children, node: _node, ...rest }: ComponentPropsWithoutRef<'pre'> & { node?: unknown }) {
  const [copied, setCopied] = useState(false);
  const copy = (e: React.MouseEvent<HTMLButtonElement>) => {
    const text = e.currentTarget.parentElement?.querySelector('code')?.textContent ?? '';
    navigator.clipboard.writeText(text.replace(/\n$/, '')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="group relative">
      <pre {...rest}>{children}</pre>
      <button
        onClick={copy}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-surface-800/80 text-surface-400 hover:text-surface-100 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
        title="Copy"
        aria-label="Copy code"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

const components: Components = { a: DocLink, pre: CodeBlock };

export default function Docs() {
  const { slug } = useParams();
  const { data, isLoading, error } = useDocs();
  const pages = data?.pages ?? [];
  const page = slug ? pages.find((p) => p.slug === slug) : pages[0];
  useBreadcrumbOverride(page && `/docs/${page.slug}`, page?.title);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 text-primary-400 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageTitle title="Docs" />
        <div className="card p-6 text-red-400">Failed to load docs: {(error as Error).message}</div>
      </div>
    );
  }

  if (pages.length === 0) {
    return (
      <div className="space-y-6">
        <PageTitle title="Docs" />
        <div className="card p-10 text-center text-surface-400">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-surface-600" />
          No documentation has been published for this installation.
        </div>
      </div>
    );
  }

  if (!page) return <Navigate to="/docs" replace />;

  return (
    <div className="space-y-6">
      <PageTitle title="Docs" />
      <div className="flex flex-col md:flex-row gap-4 md:gap-6 items-start">
        <nav className="w-full md:w-56 shrink-0 flex md:flex-col gap-1 overflow-x-auto md:sticky md:top-4">
          {pages.map((p) => (
            <NavLink
              key={p.slug}
              to={`/docs/${p.slug}`}
              className={clsx(
                'whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors',
                p.slug === page.slug
                  ? 'bg-primary-500/10 text-primary-400'
                  : 'text-surface-400 hover:bg-surface-800 hover:text-surface-200'
              )}
            >
              {p.title}
            </NavLink>
          ))}
        </nav>
        <article className="card p-6 sm:p-8 w-full min-w-0 prose prose-sm sm:prose-base dark:prose-invert max-w-none prose-pre:bg-surface-950 prose-pre:border prose-pre:border-surface-700/50 prose-a:text-primary-400 prose-code:before:content-none prose-code:after:content-none prose-code:font-normal prose-code:rounded prose-code:bg-surface-800/70 prose-code:px-1.5 prose-code:py-0.5 [&_pre_code]:bg-transparent [&_pre_code]:p-0">
          <Markdown remarkPlugins={[remarkGfm]} components={components}>
            {page.content}
          </Markdown>
        </article>
      </div>
    </div>
  );
}
