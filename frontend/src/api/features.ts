import { apiRequest } from './client';

export interface Features {
  enableTenants: boolean;
  appName?: string;
}

export function getFeatures(): Promise<Features> {
  return apiRequest<Features>('/features');
}
