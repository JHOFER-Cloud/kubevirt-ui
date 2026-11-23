import { useQuery } from '@tanstack/react-query';
import { getFeatures } from '../api/features';

export function useFeatures() {
  return useQuery({
    queryKey: ['features'],
    queryFn: getFeatures,
    staleTime: 5 * 60 * 1000,
  });
}

export const DEFAULT_APP_NAME = 'KubeVirt UI';

export function useAppName(): string {
  return useFeatures().data?.appName || DEFAULT_APP_NAME;
}
