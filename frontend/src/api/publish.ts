import { apiRequest } from './client';

export interface PublishedHost {
  name: string;
  host: string;
  port: number;
  certificate: 'Ready' | 'Pending' | 'Failed' | 'Unknown';
  message: string | null;
}

export interface PublishedResponse {
  allowed_domains: string[];
  dns_target: string;
  hosts: PublishedHost[];
}

const base = (namespace: string, vm: string) => `/namespaces/${namespace}/vms/${vm}/published`;

export function listPublished(namespace: string, vm: string): Promise<PublishedResponse> {
  return apiRequest<PublishedResponse>(base(namespace, vm));
}

export function publish(namespace: string, vm: string, data: { host: string; port: number }): Promise<PublishedHost> {
  return apiRequest<PublishedHost>(base(namespace, vm), { method: 'POST', body: data });
}

export function unpublish(namespace: string, vm: string, name: string): Promise<void> {
  return apiRequest<void>(`${base(namespace, vm)}/${name}`, { method: 'DELETE' });
}
