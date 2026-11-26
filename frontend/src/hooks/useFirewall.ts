import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as firewallApi from '@/api/firewall';

const key = (namespace: string, vm: string) => ['vm-firewall', namespace, vm];

export function useFirewall(namespace: string, vm: string) {
  return useQuery({
    queryKey: key(namespace, vm),
    queryFn: () => firewallApi.getFirewall(namespace, vm),
    enabled: !!namespace && !!vm,
  });
}

export function useSetFirewall(namespace: string, vm: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: firewallApi.Firewall) => firewallApi.setFirewall(namespace, vm, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(namespace, vm) }),
  });
}
