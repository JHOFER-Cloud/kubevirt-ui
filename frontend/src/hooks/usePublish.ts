import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as publishApi from '@/api/publish';

const key = (namespace: string, vm: string) => ['vm-published', namespace, vm];

export function usePublished(namespace: string, vm: string) {
  return useQuery({
    queryKey: key(namespace, vm),
    queryFn: () => publishApi.listPublished(namespace, vm),
    enabled: !!namespace && !!vm,
    // Certificates take a minute or two after publishing.
    refetchInterval: (query) =>
      query.state.data?.hosts.some((h) => h.certificate === 'Pending') ? 10000 : false,
  });
}

export function usePublish(namespace: string, vm: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { host: string; port: number; protocol: 'http' | 'https' }) => publishApi.publish(namespace, vm, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(namespace, vm) }),
  });
}

export function useUnpublish(namespace: string, vm: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => publishApi.unpublish(namespace, vm, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(namespace, vm) }),
  });
}
