import { describe, expect, it } from 'vitest';
import { docsHref } from '../docsHref';

describe('docsHref', () => {
  it('maps a page file to its slug', () => {
    expect(docsHref('20-dns.md')).toBe('/docs/dns');
    expect(docsHref('./ssh.md#config')).toBe('/docs/ssh#config');
    expect(docsHref('ingress')).toBe('/docs/ingress');
  });

  it('keeps in-app paths', () => {
    expect(docsHref('/profile')).toBe('/profile');
  });

  it('leaves external, anchor and scheme links alone', () => {
    for (const href of ['https://example.com', '//example.com', 'mailto:a@b.c', '#top']) {
      expect(docsHref(href)).toBeNull();
    }
  });
});
