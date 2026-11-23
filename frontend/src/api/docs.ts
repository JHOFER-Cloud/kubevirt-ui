import { apiRequest } from './client';

export interface DocPage {
  slug: string;
  title: string;
  content: string;
}

export interface DocsResponse {
  pages: DocPage[];
}

export function getDocs(): Promise<DocsResponse> {
  return apiRequest<DocsResponse>('/docs');
}
