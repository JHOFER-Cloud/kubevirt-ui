import { useState } from 'react';
import { Globe, Loader2, CheckCircle, XCircle, Trash2, Check, X, ExternalLink, Info } from 'lucide-react';
import { usePublished, usePublish, useUnpublish } from '@/hooks/usePublish';
import type { PublishedHost } from '@/api/publish';

export function hostAllowed(host: string, domains: string[]): boolean {
  return domains.some((d) => host === d || host.endsWith(`.${d}`));
}

function CertificateBadge({ host }: { host: PublishedHost }) {
  if (host.certificate === 'Ready') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-400">
        <CheckCircle className="h-3 w-3" />
        Live
      </span>
    );
  }
  if (host.certificate === 'Failed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-500/10 text-red-400">
        <XCircle className="h-3 w-3" />
        Certificate failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-500/10 text-amber-400">
      <Loader2 className="h-3 w-3 animate-spin" />
      Getting certificate
    </span>
  );
}

export function PublishTab({ vm }: { vm: { namespace: string; name: string } }) {
  const { data, isLoading } = usePublished(vm.namespace, vm.name);
  const publish = usePublish(vm.namespace, vm.name);
  const unpublish = useUnpublish(vm.namespace, vm.name);
  const [host, setHost] = useState('');
  const [port, setPort] = useState('80');
  const [protocol, setProtocol] = useState<'http' | 'https'>('http');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  if (isLoading || !data) {
    return (
      <div className="card p-8 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-surface-400" />
      </div>
    );
  }

  const domains = data.allowed_domains;
  const cleanHost = host.trim().toLowerCase().replace(/\.$/, '');
  const portNumber = Number(port);
  const portValid = Number.isInteger(portNumber) && portNumber >= 1 && portNumber <= 65535;
  const hostError =
    cleanHost && !hostAllowed(cleanHost, domains) ? `Not allowed: use ${domains.join(', ')} or a subdomain` : '';
  const canPublish = !!cleanHost && !hostError && portValid && !publish.isPending;

  const handlePublish = () => {
    if (!canPublish) return;
    publish.mutate({ host: cleanHost, port: portNumber, protocol }, { onSuccess: () => setHost('') });
  };

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="card-header">
          <h3 className="font-display text-lg font-semibold">Publish a website</h3>
          <p className="text-surface-400 text-sm mt-1">
            Make a web server in this VM reachable from the internet over HTTPS. The certificate is issued
            automatically.
          </p>
        </div>
        {domains.length === 0 ? (
          <div className="p-4">
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              Publishing is not enabled for this folder. Ask the admin to allow a domain you own.
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-4">
            <ol className="list-decimal list-inside space-y-1 text-sm text-surface-300">
              <li>
                {data.dns_target ? (
                  <>
                    At your DNS provider, add a <span className="font-mono">CNAME</span> record from the hostname to{' '}
                    <span className="font-mono text-surface-100">{data.dns_target}</span>.
                  </>
                ) : (
                  <>At your DNS provider, point the hostname at this platform (ask the admin for the target).</>
                )}
              </li>
              <li>
                Run the web server in the VM on the port below, with HTTP or HTTPS. For HTTPS, a self-signed certificate
                is fine: visitors always get the public certificate.
              </li>
              <li>Publish. HTTPS works once the certificate is issued, usually within two minutes.</li>
            </ol>
            <p className="text-xs text-surface-500">
              Allowed: <span className="font-mono">{domains.join(', ')}</span> and every subdomain, also several levels
              deep (e.g. <span className="font-mono">a.b.{domains[0]}</span>).
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handlePublish()}
                placeholder={`www.${domains[0]}`}
                aria-label="Hostname"
                className={`input flex-1 font-mono ${hostError ? 'border-red-500' : ''}`}
              />
              <input
                type="number"
                value={port}
                min={1}
                max={65535}
                onChange={(e) => setPort(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handlePublish()}
                aria-label="Port"
                className={`input sm:w-28 ${port && !portValid ? 'border-red-500' : ''}`}
              />
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value as 'http' | 'https')}
                aria-label="Protocol in the VM"
                className="input sm:w-28"
              >
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
              </select>
              <button onClick={handlePublish} disabled={!canPublish} className="btn-primary">
                {publish.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
                Publish
              </button>
            </div>
            {hostError && <p className="text-red-400 text-sm">{hostError}</p>}
            {publish.error && <p className="text-red-400 text-sm">{publish.error.message}</p>}
          </div>
        )}
      </div>

      {(domains.length > 0 || data.hosts.length > 0) && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-display font-semibold">Published hosts</h3>
          </div>
          {data.hosts.length === 0 ? (
            <div className="p-8 text-center text-surface-500">
              <Globe className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>Nothing published yet</p>
            </div>
          ) : (
            <div className="divide-y divide-surface-700">
              {data.hosts.map((h) => (
                <div key={h.name} className="px-4 py-3 flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <a
                        href={`https://${h.host}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-surface-100 hover:text-primary-400 truncate inline-flex items-center gap-1"
                      >
                        {h.host}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                      <CertificateBadge host={h} />
                    </div>
                    <p className="text-xs text-surface-500 mt-0.5">
                      to port {h.port} ({h.protocol.toUpperCase()}) in this VM
                    </p>
                    {h.certificate !== 'Ready' && (
                      <p className="text-xs text-surface-500">
                        {h.message ?? 'If this stays for more than a few minutes, check the DNS record.'}
                      </p>
                    )}
                  </div>
                  {deleteConfirm === h.name ? (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-red-400">Unpublish?</span>
                      <button
                        onClick={() =>
                          unpublish.mutate(h.name, {
                            onSuccess: () => setDeleteConfirm(null),
                          })
                        }
                        className="btn-ghost p-1 text-red-400 hover:text-red-300"
                        disabled={unpublish.isPending}
                        title="Confirm unpublish"
                      >
                        {unpublish.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button onClick={() => setDeleteConfirm(null)} className="btn-ghost p-1" title="Cancel">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setDeleteConfirm(h.name)}
                      className="btn-ghost p-1 text-surface-500 hover:text-red-400"
                      title="Unpublish"
                      aria-label={`Unpublish ${h.host}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {unpublish.error && (
            <div className="px-4 py-2 border-t border-surface-700">
              <p className="text-red-400 text-sm">{unpublish.error.message}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
