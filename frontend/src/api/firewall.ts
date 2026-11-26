import { apiRequest } from './client';

export type FirewallProtocol = 'TCP' | 'UDP' | 'ANY';

export interface FirewallRule {
  source: string | null;
  protocol: FirewallProtocol;
  ports: string;
}

export interface Firewall {
  mode: 'all' | 'rules';
  rules: FirewallRule[];
}

export interface FirewallResponse extends Firewall {
  vms: { name: string; display_name: string }[];
}

const url = (namespace: string, vm: string) => `/namespaces/${namespace}/vms/${vm}/firewall`;

export function getFirewall(namespace: string, vm: string): Promise<FirewallResponse> {
  return apiRequest<FirewallResponse>(url(namespace, vm));
}

export function setFirewall(namespace: string, vm: string, data: Firewall): Promise<Firewall> {
  return apiRequest<Firewall>(url(namespace, vm), { method: 'PUT', body: data });
}
