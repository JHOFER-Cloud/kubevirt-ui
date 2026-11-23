import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SSHKeyPicker } from '../SSHKeyPicker';

const PROFILE_KEY = 'ssh-ed25519 AAAAprofile me@laptop';
const EXTRA_KEY = 'ssh-ed25519 AAAAextra friend@pc';

vi.mock('../../../hooks/useProfile', () => ({
  useProfile: () => ({ data: { ssh_public_keys: [PROFILE_KEY] }, isLoading: false }),
}));

function Harness() {
  const [value, setValue] = useState('');
  return (
    <MemoryRouter>
      <SSHKeyPicker value={value} onChange={setValue} />
    </MemoryRouter>
  );
}

describe('SSHKeyPicker', () => {
  it('shows Profile keys as added automatically', () => {
    render(<Harness />);
    expect(screen.getByText(/added automatically/)).toBeInTheDocument();
    expect(screen.getByText(PROFILE_KEY)).toBeInTheDocument();
  });

  it('keeps an extra key visible until removed', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText(/Add a key/));
    await user.type(screen.getByPlaceholderText(/ssh-ed25519/), EXTRA_KEY);
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    expect(screen.getByText(EXTRA_KEY)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Remove extra key' }));
    expect(screen.queryByText(EXTRA_KEY)).not.toBeInTheDocument();
  });

  it('refuses a key that is already in the Profile', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText(/Add a key/));
    await user.type(screen.getByPlaceholderText(/ssh-ed25519/), PROFILE_KEY);
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    expect(screen.getByText(/already in your Profile/)).toBeInTheDocument();
  });
});
