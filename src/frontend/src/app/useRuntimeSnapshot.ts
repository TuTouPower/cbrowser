import { useRuntimeAlertsQuery } from "../features/profiles/useProfilesQuery";
import type { ApiClient } from "../shared/api/client";

export interface RuntimeSnapshot {
  coordinatorError: string | null;
}

/** t098: the global banner reads the compact alerts model — only
 * profiles with a live coordinator error. (The old running count had
 * no interface consumer and left with the all-profiles summary.) */
export function useRuntimeSnapshot(client: ApiClient): RuntimeSnapshot {
  const { data: alerts } = useRuntimeAlertsQuery(client);
  const first = (alerts?.entries ?? []).find(
    (entry) => entry.last_coordinator_error,
  );
  return {
    coordinatorError: first?.last_coordinator_error ?? null,
  };
}
