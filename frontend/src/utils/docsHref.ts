// In-app paths stay in the SPA; a bare link like `dns` or `20-dns.md` points at another docs page.
export function docsHref(href: string): string | null {
  if (/^\/(?!\/)/.test(href)) return href;
  if (/^([a-z][a-z0-9+.-]*:|\/|#)/i.test(href)) return null;
  const [path = '', hash] = href.replace(/^\.\//, '').split('#');
  const slug = path.replace(/\.md$/, '').replace(/^\d+[-_]/, '');
  return `/docs/${slug}${hash ? `#${hash}` : ''}`;
}
