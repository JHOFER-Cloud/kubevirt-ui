import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import Markdown from 'react-markdown';
import remarkAlerts from '../remarkAlerts';

function html(md: string) {
  return render(<Markdown remarkPlugins={[remarkAlerts]}>{md}</Markdown>).container;
}

describe('remarkAlerts', () => {
  it('marks a GitHub alert and strips the marker', () => {
    const quote = html('> [!IMPORTANT]\n> Coming soon').querySelector('blockquote')!;
    expect(quote.dataset.alert).toBe('important');
    expect(quote.textContent?.trim()).toBe('Coming soon');
  });

  it('accepts the text on the marker line', () => {
    const quote = html('> [!tip] Use names').querySelector('blockquote')!;
    expect(quote.dataset.alert).toBe('tip');
    expect(quote.textContent?.trim()).toBe('Use names');
  });

  it('leaves a plain quote alone', () => {
    const quote = html('> just a quote').querySelector('blockquote')!;
    expect(quote.dataset.alert).toBeUndefined();
  });
});
