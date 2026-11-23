/**
 * SSHKeyPicker — the backend always adds every Profile key, so they are shown
 * read-only; `value` is one extra key for this VM only.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Key, Plus, AlertTriangle, X, User } from 'lucide-react';
import { useProfile } from '../../hooks/useProfile';

const SSH_KEY_PREFIXES = ['ssh-rsa', 'ssh-ed25519', 'ssh-dss', 'ecdsa-sha2-', 'sk-ssh-ed25519', 'sk-ecdsa-sha2-'];

function getKeyLabel(key: string): string {
  const parts = key.trim().split(/\s+/);
  const type = parts[0]?.replace('ssh-', '').toUpperCase() || 'KEY';
  const comment = parts.length >= 3 ? parts.slice(2).join(' ') : '';
  return comment ? `${type}: ${comment}` : type;
}

function isValidSSHKey(key: string): boolean {
  return SSH_KEY_PREFIXES.some((p) => key.startsWith(p));
}

function KeyRow({ sshKey, children }: { sshKey: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-surface-700 bg-surface-800 text-sm">
      <div className="min-w-0 flex-1">
        <p className="truncate text-surface-200">{getKeyLabel(sshKey)}</p>
        <p className="text-xs font-mono text-surface-500 truncate">{sshKey}</p>
      </div>
      {children}
    </div>
  );
}

interface Props {
  value: string;
  onChange: (key: string) => void;
}

export function SSHKeyPicker({ value, onChange }: Props) {
  const { data: profile, isLoading } = useProfile();
  const [showInline, setShowInline] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [error, setError] = useState('');

  const profileKeys = profile?.ssh_public_keys ?? [];

  const handleAddInline = () => {
    const trimmed = newKey.trim();
    if (!trimmed) return;
    if (!isValidSSHKey(trimmed)) {
      setError('Invalid SSH key format');
      return;
    }
    if (profileKeys.includes(trimmed)) {
      setError('This key is already in your Profile and is added anyway');
      return;
    }
    onChange(trimmed);
    setNewKey('');
    setShowInline(false);
    setError('');
  };

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-surface-300">
        <Key className="w-4 h-4 inline mr-1" />
        SSH Keys
      </label>

      <div>
        <p className="flex items-center gap-1.5 text-xs text-surface-400 mb-1.5">
          <User className="w-3.5 h-3.5" />
          From your Profile, added automatically
          <Link to="/profile" className="ml-auto text-primary-400 hover:underline">
            Manage
          </Link>
        </p>
        {isLoading ? (
          <div className="text-xs text-surface-500 py-2">Loading keys...</div>
        ) : profileKeys.length > 0 ? (
          <div className="space-y-1.5">
            {profileKeys.map((key) => (
              <KeyRow key={key} sshKey={key} />
            ))}
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            Your Profile has no SSH keys. Add one there or a key for this VM below, otherwise you can only log in with a password or the console.
          </div>
        )}
      </div>

      <div>
        <p className="text-xs text-surface-400 mb-1.5">Extra key for this VM only</p>
        {value ? (
          <KeyRow sshKey={value}>
            <button
              type="button"
              onClick={() => onChange('')}
              className="p-1 rounded text-surface-500 hover:text-red-400 hover:bg-surface-700 transition-colors"
              title="Remove key"
              aria-label="Remove extra key"
            >
              <X className="w-4 h-4" />
            </button>
          </KeyRow>
        ) : showInline ? (
          <div className="space-y-2">
            <textarea
              value={newKey}
              onChange={(e) => { setNewKey(e.target.value); setError(''); }}
              placeholder="ssh-ed25519 AAAA... user@host"
              rows={3}
              className={`w-full px-3 py-2 bg-surface-800 border rounded-md text-surface-100 placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-xs resize-none ${
                error ? 'border-red-500' : 'border-surface-700'
              }`}
            />
            {error && (
              <div className="flex items-center gap-1 text-xs text-red-400">
                <AlertTriangle className="w-3 h-3" />
                {error}
              </div>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleAddInline}
                disabled={!newKey.trim()}
                className="btn-primary text-xs px-3 py-1.5"
              >
                Add key
              </button>
              <button
                type="button"
                onClick={() => { setShowInline(false); setNewKey(''); setError(''); }}
                className="btn-secondary text-xs px-3 py-1.5"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowInline(true)}
            className="flex items-center gap-1.5 text-xs text-primary-400 hover:text-primary-300 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add a key, e.g. for someone else
          </button>
        )}
      </div>
    </div>
  );
}
