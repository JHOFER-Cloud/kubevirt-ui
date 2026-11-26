import { useEffect, useState } from 'react';
import { Loader2, Check, Info, Plus, X } from 'lucide-react';
import { useFirewall, useSetFirewall } from '@/hooks/useFirewall';
import type { Firewall, FirewallProtocol, FirewallRule } from '@/api/firewall';

/** Same rules as the backend: '' or '80, 443, 8000-8100' within 1-65535. */
export function portsError(ports: string): string {
  for (const part of ports.split(',').map((p) => p.trim())) {
    if (!part) continue;
    const m = /^(\d{1,5})(?:-(\d{1,5}))?$/.exec(part);
    const start = m ? Number(m[1]) : NaN;
    const end = m ? Number(m[2] ?? m[1]) : NaN;
    if (!m || start < 1 || end > 65535 || start > end) return `"${part}" is not a port or range like 8000-8100`;
  }
  return '';
}

const PROTOCOLS: { value: FirewallProtocol; label: string }[] = [
  { value: 'TCP', label: 'TCP' },
  { value: 'UDP', label: 'UDP' },
  { value: 'ANY', label: 'TCP + UDP' },
];

const ANY_VM = '';

export function FirewallTab({ vm }: { vm: { namespace: string; name: string } }) {
  const { data, isLoading, error } = useFirewall(vm.namespace, vm.name);
  const save = useSetFirewall(vm.namespace, vm.name);
  const [fw, setFw] = useState<Firewall>({ mode: 'all', rules: [] });

  useEffect(() => {
    if (data) setFw({ mode: data.mode, rules: data.rules });
  }, [data]);

  if (error) {
    return (
      <div className="card p-4">
        <p className="text-red-400 text-sm">Could not load the firewall: {error.message}</p>
      </div>
    );
  }
  if (isLoading || !data) {
    return (
      <div className="card p-8 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-surface-400" />
      </div>
    );
  }

  const setRule = (i: number, patch: Partial<FirewallRule>) =>
    setFw((f) => ({ ...f, rules: f.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) }));
  const removeRule = (i: number) => setFw((f) => ({ ...f, rules: f.rules.filter((_, j) => j !== i) }));
  const addRule = () => setFw((f) => ({ ...f, rules: [...f.rules, { source: null, protocol: 'TCP', ports: '' }] }));

  const errors = fw.rules.map((r) => portsError(r.ports));
  const payload: Firewall = fw.mode === 'all' ? { mode: 'all', rules: [] } : fw;
  const saved: Firewall = { mode: data.mode, rules: data.rules };
  const dirty = JSON.stringify(payload) !== JSON.stringify(saved);
  const canSave = dirty && !save.isPending && (fw.mode === 'all' || errors.every((e) => !e));

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="font-display text-lg font-semibold">Firewall</h3>
        <p className="text-surface-400 text-sm mt-1">
          Which of your other VMs may connect to this VM, and on which ports. Changes apply within seconds, without a
          restart.
        </p>
      </div>
      <div className="p-4 space-y-4">
        <div className="space-y-2" role="radiogroup" aria-label="Who can reach this VM">
          {(
            [
              ['all', 'All VMs in this folder, on every port', 'Default.'],
              ['rules', 'Only what I allow', 'Everything not allowed below is blocked.'],
            ] as const
          ).map(([mode, label, hint]) => (
            <label key={mode} className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="firewall-mode"
                checked={fw.mode === mode}
                onChange={() => setFw((f) => ({ ...f, mode }))}
                className="mt-1"
              />
              <span>
                <span className="text-sm text-surface-100">{label}</span>
                <span className="block text-xs text-surface-500">{hint}</span>
              </span>
            </label>
          ))}
        </div>

        {fw.mode === 'rules' && (
          <div className="space-y-2">
            {fw.rules.length === 0 && (
              <p className="text-sm text-amber-300">No rules: no other VM can connect to this VM.</p>
            )}
            {fw.rules.map((r, i) => (
              <div key={i} className="rounded-lg border border-surface-700 p-2 space-y-1">
                <div className="flex flex-col sm:flex-row gap-2">
                  <select
                    value={r.source ?? ANY_VM}
                    onChange={(e) => setRule(i, { source: e.target.value || null })}
                    aria-label={`Rule ${i + 1} from`}
                    className="input sm:w-72"
                  >
                    <option value={ANY_VM}>Any VM in this folder</option>
                    {data.vms.map((v) => (
                      <option key={v.name} value={v.name}>
                        {v.display_name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={r.protocol}
                    onChange={(e) => setRule(i, { protocol: e.target.value as FirewallProtocol })}
                    aria-label={`Rule ${i + 1} protocol`}
                    className="input sm:w-32"
                  >
                    {PROTOCOLS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={r.ports}
                    onChange={(e) => setRule(i, { ports: e.target.value })}
                    placeholder="e.g. 80, 443, 8000-8100"
                    aria-label={`Rule ${i + 1} ports`}
                    className={`input flex-1 font-mono ${errors[i] ? 'border-red-500' : ''}`}
                  />
                  <button
                    onClick={() => removeRule(i)}
                    className="btn-ghost p-2 text-surface-500 hover:text-red-400 self-end sm:self-auto"
                    aria-label={`Remove rule ${i + 1}`}
                    title="Remove rule"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                {errors[i] && <p className="text-red-400 text-xs">{errors[i]}</p>}
              </div>
            ))}
            {fw.rules.length > 0 && (
              <p className="text-xs text-surface-500">
                Rules add up, their order does not matter: a VM may use every port any matching rule allows. Leave the
                ports empty to allow every port.
              </p>
            )}
            <button
              onClick={addRule}
              className="flex items-center gap-1.5 text-sm text-primary-400 hover:text-primary-300"
            >
              <Plus className="h-4 w-4" />
              Add rule
            </button>
          </div>
        )}

        <div className="flex items-start gap-2 rounded-lg border border-surface-700 bg-surface-800/50 px-3 py-2 text-xs text-surface-400">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          Always allowed: SSH through your tunnel, your published websites, and the console. Rules only limit
          connections into this VM; it can still connect out to the internet and to other VMs, as far as their firewall
          allows.
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => save.mutate(payload)} disabled={!canSave} className="btn-primary">
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Save
          </button>
          {save.error && <p className="text-red-400 text-sm">{save.error.message}</p>}
        </div>
      </div>
    </div>
  );
}
