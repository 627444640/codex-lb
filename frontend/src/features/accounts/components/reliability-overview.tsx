import { useQuery } from "@tanstack/react-query";

import { getAdmissionBreakers, getConversationHistoryCache } from "@/features/accounts/api";
import { ReliabilityCards, useSecondClock } from "@/features/accounts/components/reliability-cards";

const REFRESH_MS = 15_000;

export function ReliabilityOverview() {
  const now = useSecondClock();
  const breakers = useQuery({
    queryKey: ["accounts", "admission-breakers"],
    queryFn: getAdmissionBreakers,
    refetchInterval: REFRESH_MS,
  });
  const cache = useQuery({
    queryKey: ["accounts", "conversation-history-cache"],
    queryFn: getConversationHistoryCache,
    refetchInterval: REFRESH_MS,
  });
  if (!breakers.data || !cache.data) {
    return null;
  }
  return <ReliabilityCards breakers={breakers.data} cache={cache.data} now={now} />;
}
