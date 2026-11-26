import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FirewallTab, portsError } from '../FirewallTab';
import type { FirewallResponse } from '@/api/firewall';

const mutate = vi.fn();
let data: FirewallResponse;

vi.mock('@/hooks/useFirewall', () => ({
  useFirewall: () => ({ data, error: null, isLoading: false }),
  useSetFirewall: () => ({ mutate, isPending: false, error: null }),
}));

const vm = { namespace: 'vm-tenant2', name: 'db' };

describe('FirewallTab', () => {
  beforeEach(() => {
    mutate.mockReset();
    data = {
      mode: 'all',
      rules: [],
      vms: [
        { name: 'web-x7k2p', display_name: 'Web' },
        { name: 'app', display_name: 'app' },
      ],
    };
  });

  it('validates ports like the backend', () => {
    expect(portsError('')).toBe('');
    expect(portsError('80, 443, 8000-8100')).toBe('');
    expect(portsError('0')).not.toBe('');
    expect(portsError('90-80')).not.toBe('');
    expect(portsError('80-')).not.toBe('');
  });

  it('allows one VM on one port', async () => {
    const user = userEvent.setup();
    render(<FirewallTab vm={vm} />);
    expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled();
    await user.click(screen.getByLabelText(/Only what I allow/));
    expect(screen.getByText(/no other VM can connect/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Add rule/ }));
    await user.selectOptions(screen.getByLabelText('Rule 1 from'), 'web-x7k2p');
    await user.type(screen.getByLabelText('Rule 1 ports'), '5432');
    await user.click(screen.getByRole('button', { name: /Save/ }));
    expect(mutate).toHaveBeenCalledWith({
      mode: 'rules',
      rules: [{ source: 'web-x7k2p', protocol: 'TCP', ports: '5432' }],
    });
  });

  it('blocks saving invalid ports', async () => {
    const user = userEvent.setup();
    render(<FirewallTab vm={vm} />);
    await user.click(screen.getByLabelText(/Only what I allow/));
    await user.click(screen.getByRole('button', { name: /Add rule/ }));
    await user.type(screen.getByLabelText('Rule 1 ports'), 'http');
    expect(screen.getByText(/not a port or range/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled();
  });

  it('shows the saved rules', () => {
    data = { ...data, mode: 'rules', rules: [{ source: null, protocol: 'ANY', ports: '53' }] };
    render(<FirewallTab vm={vm} />);
    expect(screen.getByLabelText(/Only what I allow/)).toBeChecked();
    expect(screen.getByLabelText('Rule 1 from')).toHaveValue('');
    expect(screen.getByLabelText('Rule 1 protocol')).toHaveValue('ANY');
    expect(screen.getByLabelText('Rule 1 ports')).toHaveValue('53');
  });
});
