import { useQuery } from '@tanstack/react-query';
import { getDocs } from '../api/docs';

export function useDocs() {
  return useQuery({
    queryKey: ['docs'],
    queryFn: getDocs,
    staleTime: 5 * 60 * 1000,
  });
}
