import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PublishTab, hostAllowed } from '../PublishTab';
import type { PublishedResponse } from '@/api/publish';

const mutate = vi.fn();
let data: PublishedResponse;

vi.mock('@/hooks/usePublish', () => ({
  usePublished: () => ({ data, isLoading: false }),
  usePublish: () => ({ mutate, isPending: false, error: null }),
  useUnpublish: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

const vm = { namespace: 'vm-tenant2', name: 'web' };

describe('PublishTab', () => {
  beforeEach(() => {
    mutate.mockReset();
    data = { allowed_domains: ['example.com'], dns_target: 'gw.example.net', hosts: [] };
  });

  it('matches allowed domains at a dot', () => {
    expect(hostAllowed('www.example.com', ['example.com'])).toBe(true);
    expect(hostAllowed('example.com', ['example.com'])).toBe(true);
    expect(hostAllowed('evilexample.com', ['example.com'])).toBe(false);
  });

  it('says publishing is off when no domain is allowed', () => {
    data = { ...data, allowed_domains: [] };
    render(<PublishTab vm={vm} />);
    expect(screen.getByText(/not enabled for this folder/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Publish/ })).not.toBeInTheDocument();
  });

  it('shows the CNAME target and refuses a host outside the allowed domains', async () => {
    const user = userEvent.setup();
    render(<PublishTab vm={vm} />);
    expect(screen.getByText('gw.example.net')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Hostname'), 'x.other.org');
    expect(screen.getByText(/Not allowed: use example.com/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Publish/ })).toBeDisabled();
  });

  it('publishes a lowercased host and port', async () => {
    const user = userEvent.setup();
    render(<PublishTab vm={vm} />);
    await user.type(screen.getByLabelText('Hostname'), 'WWW.Example.com');
    await user.clear(screen.getByLabelText('Port'));
    await user.type(screen.getByLabelText('Port'), '8080');
    await user.click(screen.getByRole('button', { name: /Publish/ }));
    expect(mutate).toHaveBeenCalledWith({ host: 'www.example.com', port: 8080 }, expect.anything());
  });

  it('lists published hosts with their certificate state', () => {
    data = {
      ...data,
      hosts: [{ name: 'web-www', host: 'www.example.com', port: 80, certificate: 'Pending', message: null }],
    };
    render(<PublishTab vm={vm} />);
    expect(screen.getByText('www.example.com')).toBeInTheDocument();
    expect(screen.getByText('Getting certificate')).toBeInTheDocument();
    expect(screen.getByText(/check the DNS record/)).toBeInTheDocument();
  });
});
