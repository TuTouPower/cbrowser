import { useEffect } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";
import { defaultApiClient, ApiClient } from "../../shared/api/client";
import { useActionKeyMutation } from "../../shared/api/action_key_mutation";
import type {
  CandidateEntry,
  ProfileCollectionItem,
  ProfileCollectionPage,
  ProfileControlStateData,
  ProfileDeletionBatchResponse,
  ProfileDeletionOperation,
  ProfileResponse,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ProfileRuntimeProjection,
  ProfileRuntimeResponse,
  ProfileRuntimeStatusEvent,
  ProxyCollectionPage,
  ProxyCandidateEntry,
  ProxyCountryRange,
  ProxyUsedByResponse,
  ProxyProbeJob,
  ProxyProbeJobAccepted,
  ProxyProbeJobMember,
  ProxyProbeJobRequest,
  RuntimeAlertsResponse,
  GroupResponse,
  GroupCreateRequest,
  GroupUpdateRequest,
  ProxyResponse,
  ProxyCreateRequest,
  ProxyUpdateRequest,
  FontSetListResponse,
  ExtensionAssetListResponse,
  ExtensionAssetResponse,
  ExtensionUsedByResponse,
} from "../../shared/api/types";
import { ProfileEventsClient } from "../../shared/api/sse";

export const profileKeys = {
  all: ["profiles"] as const,
  lists: () => [...profileKeys.all, "list"] as const,
  detail: (id: string) => [...profileKeys.all, "detail", id] as const,
  runtime: (id: string) => [...profileKeys.all, "runtime", id] as const,
  runtimeAlerts: () => [...profileKeys.all, "runtime-alerts"] as const,
  collection: (params: object) =>
    [...profileKeys.all, "collection", params] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...profileKeys.all, "collection"] as const,
};

/** t094: server-owned probe jobs. The accepted receipt pre-seeds the detail
 * cache; SSE `probe_job_progress` events keep it current without refetching. */
export const probeJobKeys = {
  all: ["probeJobs"] as const,
  detail: (jobId: string) => [...probeJobKeys.all, "detail", jobId] as const,
};

/** t076 review f003: collection pages live under a separate key
 * prefix from the legacy full list, so every lists() invalidation
 * must also invalidate the collection prefix — otherwise a mutation
 * succeeds and the paged list keeps showing the deleted/created row
 * until the next focus refetch. */
export function invalidateProfileLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: profileKeys.collectionPrefix(),
  });
}

export function invalidateGroupLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: groupKeys.collectionPrefix(),
  });
}

export function invalidateProxyLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: proxyKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: proxyKeys.collectionPrefix(),
  });
}

export function useProfilesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse[], Error> {
  return useQuery({
    queryKey: profileKeys.lists(),
    queryFn: () => client.profiles.list(),
  });
}

export interface ProfilesCollectionParams {
  search?: string;
  group_id?: string;
  proxy_id?: string;
  status?: string;
  platform?: string;
  sort?: "default" | "manual" | "name" | "recent" | "created";
  page?: number;
  page_size?: number;
}

/** t098 (test review f001): a collection response requested before a
 * runtime event landed carries older per-row projections. When the
 * response lands it must not roll rows back: each row's projection is
 * fence-merged against the currently cached row, keeping the higher
 * revision (a missing projection is no information, never a deletion).
 * Membership, totals and profile fields always come from the fresh
 * response — only the runtime projection is revision-guarded. */
export function mergeFetchedCollectionItems(
  fetched: ProfileCollectionItem[],
  cached: ProfileCollectionItem[] | undefined,
): ProfileCollectionItem[] {
  if (!cached) return fetched;
  const cachedById = new Map(cached.map((item) => [item.id, item]));
  return fetched.map((item) => {
    const old = cachedById.get(item.id);
    if (!old?.runtime) return item;
    if (!item.runtime) return { ...item, runtime: old.runtime };
    return runtimeFenceAllows(old.runtime, item.runtime)
      ? item
      : { ...item, runtime: old.runtime };
  });
}

/** t076 AC-001: bounded server-side profile page. */
export function useProfilesCollectionQuery(
  params: ProfilesCollectionParams,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileCollectionPage, Error> {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: profileKeys.collection(params),
    queryFn: async () => {
      const page = await client.profiles.listCollection(params);
      const cached = queryClient.getQueryData<ProfileCollectionPage>(
        profileKeys.collection(params),
      );
      if (!cached) return page;
      return {
        ...page,
        items: mergeFetchedCollectionItems(
          page.items ?? [],
          cached.items ?? [],
        ),
      };
    },
  });
}

/** t076 review f008: walk every page of a profile collection query
 * until the server total is collected. One page can never stand in
 * for "all matching rows": the entry page has no pager, and even an
 * exact-status page is capped at 100 rows. The loop stops on the
 * server total, or on an empty page if the total ever disagrees.
 * The key stays under the collection prefix so list invalidations
 * refetch it. */
export function useAllProfilesCollectionQuery(
  params: Omit<ProfilesCollectionParams, "page">,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileCollectionItem[], Error> {
  const queryClient = useQueryClient();
  const queryKey = [...profileKeys.collection(params), "all-pages"] as const;
  return useQuery({
    queryKey,
    queryFn: async () => {
      const items: ProfileCollectionItem[] = [];
      let page = 1;
      for (;;) {
        const chunk = await client.profiles.listCollection({
          ...params,
          page,
          page_size: params.page_size ?? 100,
        });
        // CollectionPage.items is optional in the generated type (the
        // field carries a server default), so an absent page is an
        // empty page, not a crash.
        const pageItems = chunk.items ?? [];
        items.push(...pageItems);
        if (
          pageItems.length === 0 ||
          page * chunk.page_size >= chunk.total
        ) {
          break;
        }
        page += 1;
      }
      // Same landing guard as the paged query (test review f001):
      // events merged during the walk must survive its result.
      const cached =
        queryClient.getQueryData<ProfileCollectionItem[]>(queryKey);
      return cached ? mergeFetchedCollectionItems(items, cached) : items;
    },
  });
}

/** t098: compact read model for the global coordinator-error banner —
 * only profiles with a live coordinator error. Row runtime state
 * travels with the collection page itself. */
export function useRuntimeAlertsQuery(
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<RuntimeAlertsResponse, Error> {
  return useQuery({
    queryKey: profileKeys.runtimeAlerts(),
    queryFn: () => client.profiles.getRuntimeAlerts(),
    enabled: options.enabled ?? true,
  });
}

/** t076 AC-006: bounded profile name search. */
export function useProfileCandidatesQuery(
  search: string,
  limit = 20,
  client: ApiClient = defaultApiClient,
): UseQueryResult<CandidateEntry[], Error> {
  return useQuery({
    queryKey: [...profileKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.profiles.listCandidates(search, limit),
  });
}

/** t076 review f006: bounded group name search, for filter options
 * and move menus that must not fetch the whole group table. */
export function useGroupCandidatesQuery(
  search: string,
  limit = 50,
  client: ApiClient = defaultApiClient,
): UseQueryResult<CandidateEntry[], Error> {
  return useQuery({
    queryKey: [...groupKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.groups.listCandidates(search, limit),
  });
}

/** t076 review f006: bounded proxy name search, for filter options
 * that must not fetch the whole proxy table. */
export function useProxyCandidatesQuery(
  search: string,
  limit = 50,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCandidateEntry[], Error> {
  return useQuery({
    queryKey: [...proxyKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.proxies.listCandidates(search, limit),
  });
}

/** t076 review f006: one group by id — echoes a selected filter
 * value that falls outside the bounded candidate page. */
export function useGroupQuery(
  groupId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<GroupResponse, Error> {
  return useQuery({
    queryKey: [...groupKeys.all, "detail", groupId || ""] as const,
    queryFn: () => client.groups.get(groupId!),
    enabled: Boolean(groupId),
  });
}

/** t076 review f006: one proxy by id — echoes a selected filter
 * value that falls outside the bounded candidate page. */
export function useProxyQuery(
  proxyId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyResponse, Error> {
  return useQuery({
    queryKey: [...proxyKeys.all, "detail", proxyId || ""] as const,
    queryFn: () => client.proxies.get(proxyId!),
    enabled: Boolean(proxyId),
  });
}

export function useProfileQuery(
  profileId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse, Error> {
  return useQuery({
    queryKey: profileKeys.detail(profileId || ""),
    queryFn: () => client.profiles.get(profileId!),
    enabled: Boolean(profileId),
  });
}

export function useProfileRuntimeQuery(
  profileId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileRuntimeResponse, Error> {
  return useQuery({
    queryKey: profileKeys.runtime(profileId || ""),
    queryFn: () => client.profiles.getRuntime(profileId!),
    enabled: Boolean(profileId),
  });
}

export function useCreateProfileMutation(
  client: ApiClient = defaultApiClient,
  keyOptions?: { keySource?: () => string },
): UseMutationResult<ProfileResponse, Error, ProfileCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation(
    {
      mutationFn: ({ input, actionKey }) =>
        client.profiles.create(input, actionKey),
      onSuccess: () => {
        invalidateProfileLists(queryClient);
        queryClient.invalidateQueries({ queryKey: extensionKeys.all });
      },
    },
    keyOptions,
  );
}

export function useUpdateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, { id: string; data: ProfileUpdateRequest }> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.update(input.id, input.data, actionKey),
    onSuccess: async (data, { input }) => {
      // t058 A24: cancel any in-flight detail fetch before writing the
      // saved profile, so a stale GET resolving after the save cannot
      // overwrite it. The detail query is not invalidated — invalidation
      // would refetch and could reintroduce the same race — only the
      // list is invalidated.
      await queryClient.cancelQueries({
        queryKey: profileKeys.detail(input.id),
      });
      queryClient.setQueryData(profileKeys.detail(input.id), data);
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: extensionKeys.all });
    },
  });
}

export function useDeleteProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.delete(input, actionKey),
    onSuccess: () => {
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: extensionKeys.all });
    },
  });
}

/** t078: deletion lifecycle hooks. The batch query polls while any
 * target is non-terminal and invalidates the profile lists as targets
 * reach ``done``, so the list converges even if the progress dialog
 * is closed mid-run (the intent itself is durable server-side). */
export const deletionKeys = {
  all: ["profile-deletions"] as const,
  batch: (batchId: string) =>
    [...deletionKeys.all, "batch", batchId] as const,
};

export function useCreateDeletionsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileDeletionBatchResponse, Error, string[]> {
  return useMutation({
    mutationFn: (profileIds: string[]) =>
      client.profiles.createDeletions(profileIds),
  });
}

export function useDeletionBatchQuery(
  batchId: string | null,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileDeletionBatchResponse> {
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: deletionKeys.batch(batchId ?? ""),
    queryFn: () => client.profiles.getDeletionBatch(batchId!),
    enabled: batchId !== null,
    refetchInterval: (query) => {
      const operations = query.state.data?.operations ?? [];
      return operations.some(
        (op) => op.stage !== "done" && op.stage !== "failed",
      )
        ? 1000
        : false;
    },
  });
  const doneIds = (result.data?.operations ?? [])
    .filter((op) => op.stage === "done")
    .map((op) => op.profile_id)
    .join(",");
  useEffect(() => {
    if (doneIds) {
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: extensionKeys.all });
    }
  }, [doneIds, queryClient]);
  return result;
}

export function useRetryDeletionMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileDeletionOperation, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (operationId: string) =>
      client.profiles.retryDeletion(operationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: deletionKeys.all });
    },
  });
}

export function useDuplicateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProfileResponse,
  Error,
  { id: string; includeBrowserState: boolean; name?: string }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.duplicate(
        input.id,
        { include_browser_state: input.includeBrowserState, name: input.name },
        actionKey,
      ),
    onSuccess: () => {
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: extensionKeys.all });
    },
  });
}

export function useResetProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.reset(input, actionKey),
    onSuccess: (data) => {
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(data.id) });
    },
  });
}

export interface ProfileScopedMutationState {
  isPending: boolean;
  isError: boolean;
  error: Error | null;
}

/**
 * Scopes a shared mutation hook's visible state to one Profile.
 *
 * Components such as AppLayout stay mounted across Profile switches, so
 * the raw mutation result would show Profile A's error (and pending
 * disablement) while the user is looking at Profile B, and A's late
 * settle would repaint B's view. The mutation's target is read from its
 * variables — for action-key mutations the wrapped `{ input, actionKey }`
 * shape is unwrapped — and state is only surfaced when the target is the
 * Profile currently on screen. Mutation side effects (query cache
 * writes) are already keyed by the target id and are unaffected.
 */
export function scopeMutationToProfile<TData, TVariables>(
  mutation: UseMutationResult<TData, Error, TVariables>,
  profileId: string | null | undefined,
  targetOf: (input: TVariables) => string | null | undefined,
): ProfileScopedMutationState {
  const rawVariables = (mutation as { variables?: unknown }).variables;
  const input =
    rawVariables && typeof rawVariables === "object" && "input" in rawVariables
      ? (rawVariables as { input: TVariables }).input
      : (rawVariables as TVariables | undefined);
  const target = input != null ? targetOf(input) : undefined;
  const matches = target != null && profileId != null && target === profileId;
  return {
    isPending: matches && mutation.isPending,
    isError: matches && mutation.isError,
    error: matches ? mutation.error : null,
  };
}

export function useSetDesiredStateMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProfileRuntimeResponse,
  Error,
  { id: string; state: "running" | "stopped" }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.setDesiredState(input.id, input.state, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input.id), data);
      applyRuntimeResponseToCollections(queryClient, data);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useRetrySearchDefaultsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.retrySearchDefaults(input, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input), data);
    },
  });
}

export function useRestoreControlMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileControlStateData, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.restoreControl(input, actionKey),
    onSuccess: (data, { input }) => {
      // The restore endpoint returns only the control state; merge it
      // into the cached runtime response (SSE will confirm it next).
      queryClient.setQueryData(
        profileKeys.runtime(input),
        (old: ProfileRuntimeResponse | undefined) => {
          if (!old) return old;
          return { ...old, control: data };
        },
      );
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(input) });
    },
  });
}

export function useStopProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.stop(input, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input), data);
      applyRuntimeResponseToCollections(queryClient, data);
      invalidateProfileLists(queryClient);
    },
  });
}

const APPLY_POLL_INTERVAL_MS = 500;
const APPLY_PROBE_TIMEOUT_MS = 30_000;
const APPLY_STOP_TIMEOUT_MS = 120_000;
const APPLY_START_TIMEOUT_MS = 180_000;

/**
 * Stage record for one apply action, keyed by its action key so React
 * Query retries of the same logical action resume where the previous
 * attempt left off. Entries are removed when the action converges; a
 * permanently failed action leaves one small entry behind, bounded by
 * the number of failed actions in the page session.
 */
interface ApplyStage {
  /** Whether the pre-action runtime has been observed at least once. */
  observed: boolean;
  /** runtime_instance_id seen before this action's stop step. */
  preStopInstanceId: string | null;
  /** setDesiredState("running") has been invoked for this action. */
  startRequested: boolean;
}

const applyStages = new Map<string, ApplyStage>();

function getApplyStage(actionKey: string): ApplyStage {
  let stage = applyStages.get(actionKey);
  if (!stage) {
    stage = { observed: false, preStopInstanceId: null, startRequested: false };
    applyStages.set(actionKey, stage);
  }
  return stage;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForRuntimeState(
  client: ApiClient,
  profileId: string,
  predicate: (runtime: ProfileRuntimeResponse) => boolean,
  timeoutMs: number,
): Promise<ProfileRuntimeResponse> {
  const deadline = Date.now() + timeoutMs;
  let last: ProfileRuntimeResponse | null = null;
  let consecutiveFailures = 0;
  while (Date.now() < deadline) {
    try {
      last = await client.profiles.getRuntime(profileId);
      consecutiveFailures = 0;
      if (predicate(last)) {
        return last;
      }
    } catch (err) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= 3) {
        throw new Error(
          `Runtime polling failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
    await sleep(APPLY_POLL_INTERVAL_MS);
  }
  throw new Error(`Profile runtime did not converge before timeout: ${JSON.stringify(last)}`);
}

export function useApplyDisplaySettingsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: async ({ input: id, actionKey }) => {
      // One apply call is one logical action; its stop and start steps are
      // distinct backend operations, so each derives its own stable key
      // from the action key. A retry of the whole action reuses both.
      const stopOperationKey = `${actionKey}:stop`;
      const startOperationKey = `${actionKey}:start`;
      const stage = getApplyStage(actionKey);

      // Resume from observation, not from the top: a retry first looks at
      // where the previous attempt actually left the runtime. Replaying
      // the stop step is not harmless — the server replays an already
      // applied stop key as a no-op, so the new instance would never be
      // stopped and a wait for "stopped" could only time out (p018).
      // The probe is bounded by the polling helper (three consecutive
      // query failures or the probe deadline produce an error).
      const current = await waitForRuntimeState(
        client,
        id,
        () => true,
        APPLY_PROBE_TIMEOUT_MS,
      );
      if (!stage.observed) {
        stage.observed = true;
        stage.preStopInstanceId = current.runtime_instance_id ?? null;
      }

      // The start step already took effect on the server but its response
      // was lost: the runtime is converging back to running. Skip both
      // sends and converge on running; never stop or rebuild the new
      // instance. "Already effective" needs evidence that the running
      // instance is the one this action started: when both the pre-stop
      // instance id and the current instance id are known they must
      // differ — desired/observed alone cannot distinguish a genuinely
      // new instance from the pre-stop instance restored by an external
      // actor. When either id is unknown, fall back to the
      // desired/observed heuristic.
      const currentInstanceId = current.runtime_instance_id ?? null;
      const instanceEvidence =
        stage.preStopInstanceId === null ||
        currentInstanceId === null ||
        currentInstanceId !== stage.preStopInstanceId;
      const startAlreadyEffective =
        stage.startRequested &&
        instanceEvidence &&
        current.desired_state === "running" &&
        (current.observed_state === "running" ||
          current.observed_state === "starting");

      if (!startAlreadyEffective) {
        if (current.observed_state !== "stopped") {
          await client.profiles.stop(id, stopOperationKey);
          await waitForRuntimeState(
            client,
            id,
            (runtime) => runtime.observed_state === "stopped",
            APPLY_STOP_TIMEOUT_MS,
          );
        }
        // Record the intent before the call: if the response is lost,
        // the retry distinguishes "start applied" from "never sent" by
        // observing the runtime state (see startAlreadyEffective).
        stage.startRequested = true;
        await client.profiles.setDesiredState(id, "running", startOperationKey);
      }
      const final = await waitForRuntimeState(
        client,
        id,
        (runtime) =>
          runtime.desired_state === "running" &&
          runtime.observed_state === "running",
        APPLY_START_TIMEOUT_MS,
      );
      applyStages.delete(actionKey);
      return final;
    },
    onSuccess: (data, { input: id }) => {
      queryClient.setQueryData(profileKeys.runtime(id), data);
      applyRuntimeResponseToCollections(queryClient, data);
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(id) });
    },
  });
}

/** Fields shared by the per-profile runtime response and a
 * collection row's runtime projection — an SSE runtime event merges
 * into both from the same fields. */
interface RuntimeSharedFields {
  desired_state: "stopped" | "running";
  observed_state: "stopped" | "starting" | "running" | "stopping" | "error";
  runtime_instance_id?: string | null;
  config_version: number;
  state_revision?: number;
  failure_count: number;
  restart_blocked: boolean;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  last_coordinator_error?: string | null;
  updated_at: string;
}

interface RuntimeFenceFields {
  state_revision?: number | null;
  config_version: number;
  runtime_instance_id?: string | null;
}

/** t098: the single fence shared by collection reads, operation
 * results and SSE events. ``state_revision`` is a per-profile
 * monotonic counter bumped on every runtime write, so it decides on
 * its own whenever both sides carry it — an instance replacement at
 * the same config version, or a config rollback, can no longer slip
 * an older fact past it. The config-version + instance pair remains
 * only as the fallback for a peer that predates the revision. */
export function runtimeFenceAllows(
  cached: RuntimeFenceFields,
  incoming: RuntimeFenceFields,
): boolean {
  if (cached.state_revision != null && incoming.state_revision != null) {
    return incoming.state_revision >= cached.state_revision;
  }
  const incomingVersion = incoming.config_version ?? cached.config_version;
  if (incomingVersion < cached.config_version) return false;
  if (
    incomingVersion === cached.config_version &&
    incoming.runtime_instance_id != null &&
    cached.runtime_instance_id != null &&
    incoming.runtime_instance_id !== cached.runtime_instance_id
  ) {
    return false;
  }
  return true;
}

type ObservedState = ProfileRuntimeProjection["observed_state"];

/** Whether an observed state belongs to a collection page's status
 * filter bucket (mirrors the server-side bucketing). Only the status
 * filter couples membership to runtime state. */
function statusBucketIncludes(
  status: string | undefined,
  observed: ObservedState,
): boolean {
  switch (status) {
    case undefined:
    case "all":
      return true;
    case "running":
      return observed === "running" || observed === "starting";
    case "running_exact":
      return observed === "running";
    case "stopped":
      return observed === "stopped" || observed === "stopping";
    case "error":
      return observed === "error";
    default:
      return true;
  }
}

function projectionFromEvent(
  event: ProfileRuntimeStatusEvent,
): ProfileRuntimeProjection {
  return {
    desired_state: event.desired_state,
    observed_state: event.observed_state,
    config_version: event.config_version ?? 1,
    state_revision: event.state_revision ?? 0,
    runtime_instance_id: event.runtime_instance_id ?? null,
    failure_count: event.failure_count ?? 0,
    restart_blocked: event.restart_blocked ?? false,
    last_started_at: event.last_started_at ?? null,
    last_stopped_at: event.last_stopped_at ?? null,
    preview_captured_at: null,
    last_coordinator_error: event.last_coordinator_error ?? null,
    updated_at: event.updated_at,
  };
}

function mergeProjection(
  base: ProfileRuntimeProjection,
  event: ProfileRuntimeStatusEvent,
): ProfileRuntimeProjection {
  return {
    ...base,
    desired_state: event.desired_state ?? base.desired_state,
    observed_state: event.observed_state ?? base.observed_state,
    runtime_instance_id:
      event.runtime_instance_id !== undefined
        ? event.runtime_instance_id
        : base.runtime_instance_id,
    config_version: event.config_version ?? base.config_version,
    state_revision: event.state_revision ?? base.state_revision,
    failure_count: event.failure_count ?? base.failure_count,
    restart_blocked: event.restart_blocked ?? base.restart_blocked,
    last_started_at:
      event.last_started_at !== undefined
        ? event.last_started_at
        : base.last_started_at,
    last_stopped_at:
      event.last_stopped_at !== undefined
        ? event.last_stopped_at
        : base.last_stopped_at,
    last_coordinator_error:
      event.last_coordinator_error !== undefined
        ? event.last_coordinator_error
        : base.last_coordinator_error,
    updated_at: event.updated_at ?? base.updated_at,
  };
}

function projectionsEqual(
  a: ProfileRuntimeProjection,
  b: ProfileRuntimeProjection,
): boolean {
  return (
    a.desired_state === b.desired_state &&
    a.observed_state === b.observed_state &&
    a.runtime_instance_id === b.runtime_instance_id &&
    a.config_version === b.config_version &&
    a.state_revision === b.state_revision &&
    a.failure_count === b.failure_count &&
    a.restart_blocked === b.restart_blocked &&
    a.last_started_at === b.last_started_at &&
    a.last_stopped_at === b.last_stopped_at &&
    a.preview_captured_at === b.preview_captured_at &&
    a.last_coordinator_error === b.last_coordinator_error &&
    a.updated_at === b.updated_at
  );
}

interface CollectionCacheHit {
  queryKey: readonly unknown[];
  isAllPages: boolean;
  params: ProfilesCollectionParams;
  page: ProfileCollectionPage | null;
  items: ProfileCollectionItem[];
  index: number;
}

function collectionCaches(
  queryClient: QueryClient,
): CollectionCacheHit[] {
  const hits: CollectionCacheHit[] = [];
  const caches = queryClient.getQueriesData<unknown>({
    queryKey: profileKeys.collectionPrefix(),
  });
  for (const [queryKey, data] of caches) {
    if (!data) continue;
    const isAllPages = queryKey[queryKey.length - 1] === "all-pages";
    const params = (queryKey[2] ?? {}) as ProfilesCollectionParams;
    if (isAllPages) {
      const items = data as ProfileCollectionItem[];
      hits.push({
        queryKey,
        isAllPages,
        params,
        page: null,
        items,
        index: -1,
      });
    } else {
      const page = data as ProfileCollectionPage;
      hits.push({
        queryKey,
        isAllPages,
        params,
        page,
        items: page.items ?? [],
        index: -1,
      });
    }
  }
  return hits;
}

/** t101: a per-profile high-water mark of observed state revisions,
 * keyed by QueryClient so separate mounts and tests stay isolated. The
 * mark survives cache invalidations, so a profile whose rows were
 * evicted still suppresses events older than a revision we already
 * saw. */
const seenRevisionByClient = new WeakMap<QueryClient, Map<string, number>>();

function recordSeenRevision(
  queryClient: QueryClient,
  profileId: string,
  revision: number,
): void {
  let byProfile = seenRevisionByClient.get(queryClient);
  if (!byProfile) {
    byProfile = new Map();
    seenRevisionByClient.set(queryClient, byProfile);
  }
  const seen = byProfile.get(profileId);
  if (seen == null || revision > seen) byProfile.set(profileId, revision);
}

interface RevisionWitness {
  maxRevision: number | null;
  duplicate: boolean;
}

/** t101: the unified witness for whether an event is history or a
 * replay. The highest revision known for a profile is aggregated from
 * the runtime cache, every collection row and the persistent watermark;
 * no single cache needs to be populated (f003). A replay counts as a
 * duplicate only when a known projection at the same revision matches
 * the event payload (the "same revision, same state" case). */
function revisionWitness(
  queryClient: QueryClient,
  event: ProfileRuntimeStatusEvent,
): RevisionWitness {
  const eventRevision = event.state_revision ?? 0;
  const fromEvent = projectionFromEvent(event);
  let maxRevision =
    seenRevisionByClient.get(queryClient)?.get(event.profile_id) ?? null;
  let duplicate = false;
  const consider = (row: ProfileRuntimeProjection): void => {
    const revision = row.state_revision;
    if (revision == null) return;
    if (maxRevision == null || revision > maxRevision) {
      maxRevision = revision;
      duplicate = false;
    }
    if (revision === eventRevision && projectionsEqual(row, fromEvent)) {
      duplicate = true;
    }
  };
  const runtime = queryClient.getQueryData<ProfileRuntimeResponse>(
    profileKeys.runtime(event.profile_id),
  );
  if (runtime) {
    consider({
      desired_state: runtime.desired_state,
      observed_state: runtime.observed_state,
      config_version: runtime.config_version,
      state_revision: runtime.state_revision,
      runtime_instance_id: runtime.runtime_instance_id,
      failure_count: runtime.failure_count,
      restart_blocked: runtime.restart_blocked,
      last_started_at: runtime.last_started_at,
      last_stopped_at: runtime.last_stopped_at,
      preview_captured_at: runtime.preview_captured_at,
      last_coordinator_error: runtime.last_coordinator_error,
      updated_at: runtime.updated_at,
    });
  }
  for (const hit of collectionCaches(queryClient)) {
    for (const item of hit.items) {
      if (item.id === event.profile_id && item.runtime) {
        consider(item.runtime);
      }
    }
  }
  return { maxRevision, duplicate };
}

function writeCollectionCache(
  queryClient: QueryClient,
  hit: CollectionCacheHit,
  items: ProfileCollectionItem[],
): void {
  if (hit.isAllPages) {
    queryClient.setQueryData(hit.queryKey, items);
  } else {
    queryClient.setQueryData(hit.queryKey, { ...hit.page, items });
  }
}

/** t098: merge one runtime event into every cached collection page,
 * in place, under the shared revision fence. Rows are only ever
 * updated — an event never synthesizes a row (a late event for a
 * deleted or off-page profile cannot resurrect it). When the merged
 * state crosses the page's status-filter boundary, or a non-member's
 * new state enters the page's status bucket, the page is invalidated
 * so the server reconverges membership and total. Returns whether
 * anything changed (a duplicate/stale event changes nothing and must
 * have no side effects). */
export function applyRuntimeEventToCollections(
  queryClient: QueryClient,
  event: ProfileRuntimeStatusEvent,
  options: { suppressInvalidation?: boolean } = {},
): boolean {
  let changed = false;
  for (const hit of collectionCaches(queryClient)) {
    const index = hit.items.findIndex((item) => item.id === event.profile_id);
    if (index === -1) {
      // Only a status-filtered page can gain a member from a state
      // change; unfiltered membership is driven by create/delete.
      if (
        !options.suppressInvalidation &&
        hit.params.status &&
        hit.params.status !== "all" &&
        statusBucketIncludes(hit.params.status, event.observed_state)
      ) {
        queryClient.invalidateQueries({ queryKey: hit.queryKey });
        changed = true;
      }
      continue;
    }
    const item = hit.items[index];
    if (!item) continue;
    if (item.runtime && !runtimeFenceAllows(item.runtime, event)) continue;
    const nextRuntime = item.runtime
      ? mergeProjection(item.runtime, event)
      : projectionFromEvent(event);
    if (item.runtime && projectionsEqual(nextRuntime, item.runtime)) {
      continue;
    }
    const wasIn = item.runtime
      ? statusBucketIncludes(hit.params.status, item.runtime.observed_state)
      : true;
    const isIn = statusBucketIncludes(
      hit.params.status,
      nextRuntime.observed_state,
    );
    if (wasIn !== isIn) {
      // t101 (f004): when the event is history/replay its side effects
      // are suppressed. Crossing a filter boundary is a membership
      // change the server owns — write-back here would leave a stale
      // row in the wrong bucket with an unchanged total until an
      // unrelated refetch. Skip it entirely and let the next server
      // read reconverge.
      if (options.suppressInvalidation) continue;
      queryClient.invalidateQueries({ queryKey: hit.queryKey });
      changed = true;
      continue;
    }
    const nextItems = hit.items.slice();
    nextItems[index] = { ...item, runtime: nextRuntime };
    writeCollectionCache(queryClient, hit, nextItems);
    changed = true;
  }
  return changed;
}

/** t098: an operation result (start/stop/apply response) merges into
 * cached collection rows under the same revision fence — a repeated
 * same-revision result never rolls a row that has since advanced
 * back. Filter-boundary crossings invalidate the page instead. */
export function applyRuntimeResponseToCollections(
  queryClient: QueryClient,
  runtime: ProfileRuntimeResponse,
): void {
  for (const hit of collectionCaches(queryClient)) {
    const index = hit.items.findIndex(
      (item) => item.id === runtime.profile_id,
    );
    if (index === -1) continue;
    const item = hit.items[index];
    if (!item) continue;
    if (item.runtime && !runtimeFenceAllows(item.runtime, runtime)) {
      continue;
    }
    const nextRuntime: ProfileRuntimeProjection = {
      desired_state: runtime.desired_state,
      observed_state: runtime.observed_state,
      config_version: runtime.config_version,
      state_revision: runtime.state_revision ?? 0,
      runtime_instance_id: runtime.runtime_instance_id ?? null,
      failure_count: runtime.failure_count,
      restart_blocked: runtime.restart_blocked,
      last_started_at: runtime.last_started_at ?? null,
      last_stopped_at: runtime.last_stopped_at ?? null,
      preview_captured_at: runtime.preview_captured_at ?? null,
      last_coordinator_error: runtime.last_coordinator_error ?? null,
      updated_at: runtime.updated_at,
    };
    if (item.runtime && projectionsEqual(nextRuntime, item.runtime)) {
      continue;
    }
    const wasIn = item.runtime
      ? statusBucketIncludes(hit.params.status, item.runtime.observed_state)
      : true;
    const isIn = statusBucketIncludes(
      hit.params.status,
      nextRuntime.observed_state,
    );
    if (wasIn !== isIn) {
      queryClient.invalidateQueries({ queryKey: hit.queryKey });
      continue;
    }
    const nextItems = hit.items.slice();
    nextItems[index] = { ...item, runtime: nextRuntime };
    writeCollectionCache(queryClient, hit, nextItems);
  }
}

export function useProfileEventsSync(sseClient: ProfileEventsClient): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = sseClient.onEvent((event) => {
      const old = queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime(event.profile_id),
      );
      // t101 (review f001): compute the suppression witness BEFORE any
      // cache write. The runtime cache is about to be updated with this
      // very event; reading it afterwards would make every fresh event
      // look like a replay of itself and swallow legitimate
      // invalidations. Every witness input (runtime cache, collection
      // rows, watermark) is still in its pre-event state here.
      const witness = revisionWitness(queryClient, event);
      const eventRevision = event.state_revision ?? 0;
      const eventIsSuppressed =
        (witness.maxRevision != null && eventRevision < witness.maxRevision) ||
        witness.duplicate;
      // t098: each cache fences by its OWN revision. The caches
      // usually disagree (a collection page is refetched on focus;
      // the runtime cache only on a detail visit), so one fence taken
      // from whichever cache exists first would let a late event roll
      // the newer cache back. An event below a cache's revision
      // skips that cache only and may still update the other one.
      const mergeShared = <T extends RuntimeSharedFields>(base: T): T => ({
        ...base,
        desired_state: event.desired_state ?? base.desired_state,
        observed_state: event.observed_state ?? base.observed_state,
        runtime_instance_id:
          event.runtime_instance_id !== undefined
            ? event.runtime_instance_id
            : base.runtime_instance_id,
        config_version: event.config_version ?? base.config_version,
        state_revision: event.state_revision ?? base.state_revision,
        failure_count: event.failure_count ?? base.failure_count,
        restart_blocked: event.restart_blocked ?? base.restart_blocked,
        last_started_at:
          event.last_started_at !== undefined
            ? event.last_started_at
            : base.last_started_at,
        last_stopped_at:
          event.last_stopped_at !== undefined
            ? event.last_stopped_at
            : base.last_stopped_at,
        last_coordinator_error:
          event.last_coordinator_error !== undefined
            ? event.last_coordinator_error
            : base.last_coordinator_error,
        updated_at: event.updated_at ?? base.updated_at,
      });
      const sharedChanged = (
        next: RuntimeSharedFields,
        base: RuntimeSharedFields,
      ): boolean =>
        next.observed_state !== base.observed_state ||
        next.desired_state !== base.desired_state ||
        next.runtime_instance_id !== base.runtime_instance_id ||
        next.config_version !== base.config_version ||
        next.state_revision !== base.state_revision ||
        next.failure_count !== base.failure_count ||
        next.restart_blocked !== base.restart_blocked ||
        next.last_started_at !== base.last_started_at ||
        next.last_stopped_at !== base.last_stopped_at ||
        next.last_coordinator_error !== base.last_coordinator_error ||
        next.updated_at !== base.updated_at;
      // Per-profile runtime entry: update in place when cached, never
      // synthesize one from an event — and only when this cache's own
      // fence let the event through.
      let runtimeChanged = false;
      if (old && runtimeFenceAllows(old, event)) {
        const nextRuntime: ProfileRuntimeResponse = {
          ...mergeShared(old),
          search_defaults:
            event.search_defaults !== undefined
              ? event.search_defaults
              : old.search_defaults,
          transport:
            event.transport !== undefined
              ? event.transport
              : old.transport,
          control:
            // t031 (review f006): SSE is normally ordered, but a
            // delayed or replayed event must not overwrite newer
            // generation state: only apply control at or above the
            // cached generation.
            event.control != null &&
            (old.control == null ||
              event.control.generation >= old.control.generation)
              ? event.control
              : old.control,
        };
        runtimeChanged =
          sharedChanged(nextRuntime, old) ||
          nextRuntime.control !== old.control ||
          nextRuntime.search_defaults !== old.search_defaults ||
          nextRuntime.transport !== old.transport;
        if (runtimeChanged) {
          queryClient.setQueryData(
            profileKeys.runtime(event.profile_id),
            nextRuntime,
          );
        }
      }
      // t098 / t101: the same event merges into every cached page under
      // its own fence. A history/replay event changes nothing anywhere
      // and has no side effects; a fresh event still invalidates
      // filtered pages and alerts normally.
      applyRuntimeEventToCollections(queryClient, event, {
        suppressInvalidation: eventIsSuppressed,
      });
      // Global coordinator-error banner: the compact alerts read
      // model is invalidated only when this event actually changes
      // the profile's alert membership/message.
      if (!eventIsSuppressed && event.last_coordinator_error !== undefined) {
        const alerts = queryClient.getQueryData<RuntimeAlertsResponse>(
          profileKeys.runtimeAlerts(),
        );
        if (alerts) {
          const existing = alerts.entries.find(
            (entry) => entry.profile_id === event.profile_id,
          );
          if (
            (existing?.last_coordinator_error ?? null) !==
            event.last_coordinator_error
          ) {
            queryClient.invalidateQueries({
              queryKey: profileKeys.runtimeAlerts(),
            });
          }
        }
      }
      // t101: advance the watermark to the highest revision this client
      // has now seen for the profile. New events raise it; history and
      // replays leave it at its current high mark.
      recordSeenRevision(
        queryClient,
        event.profile_id,
        Math.max(witness.maxRevision ?? 0, eventRevision),
      );
    });

    const unsubscribePreview: (() => void) | undefined =
      sseClient.onPreviewEvent?.((event) => {
        const detail = queryClient.getQueryData<ProfileResponse>(
          profileKeys.detail(event.profile_id),
        );
        const listed = queryClient
          .getQueryData<ProfileResponse[]>(profileKeys.lists())
          ?.find((item) => item.id === event.profile_id);
        // List pages read the collection pages now, so the legacy full
        // list is usually empty there — consult the cached collection
        // pages for the preview policy as well.
        const inCollection = queryClient
          .getQueriesData<ProfileCollectionPage>({
            queryKey: profileKeys.collectionPrefix(),
          })
          .flatMap(([, page]) => page?.items ?? [])
          .find((item) => item.id === event.profile_id);
        if (
          detail?.capture_preview === false ||
          listed?.capture_preview === false ||
          inCollection?.capture_preview === false
        )
          return;
        const profile = detail ?? listed ?? inCollection;
        if (profile?.capture_preview !== true) return;
        const captured = Date.parse(event.captured_at);
        if (!Number.isFinite(captured)) return;
        // A preview capture also moves the collection row's
        // projection the list renders, under the same "captured time
        // never goes backwards" fence as the runtime entry.
        queryClient.setQueryData(
          profileKeys.runtime(event.profile_id),
          (old: ProfileRuntimeResponse | undefined) => {
            if (!old) return undefined;
            const previous = old.preview_captured_at
              ? Date.parse(old.preview_captured_at)
              : NaN;
            if (Number.isFinite(previous) && captured <= previous) return old;
            return { ...old, preview_captured_at: event.captured_at };
          },
        );
        for (const hit of collectionCaches(queryClient)) {
          const index = hit.items.findIndex(
            (item) => item.id === event.profile_id,
          );
          if (index === -1) continue;
          const item = hit.items[index];
          if (!item || !item.runtime) continue;
          const previous = item.runtime.preview_captured_at
            ? Date.parse(item.runtime.preview_captured_at)
            : NaN;
          if (Number.isFinite(previous) && captured <= previous) continue;
          const nextItems = hit.items.slice();
          nextItems[index] = {
            ...item,
            runtime: {
              ...item.runtime,
              preview_captured_at: event.captured_at,
            },
          };
          writeCollectionCache(queryClient, hit, nextItems);
        }
      });

    // t056 A31: another client's group/proxy write arrives as a
    // reference event — invalidate the reference lists and the Profile
    // list (a profile's group/proxy may have changed) and refetch.
    const unsubscribeReference: (() => void) | undefined =
      sseClient.onReferenceEvent?.((event) => {
        if (event.event === "groups_changed") {
          invalidateGroupLists(queryClient);
        } else {
          invalidateProxyLists(queryClient);
        }
        invalidateProfileLists(queryClient);
      });

    // t095 AC-002: 一次成员状态迁移的 probe_job_progress 事件同时驱动
    // 进度读模型与代理列表刷新。观测已先于事件落库，失效列表即取回最新
    // 逐条结果；不靠固定间隔轮询。
    const unsubscribeProbeJob: (() => void) | undefined =
      sseClient.onProbeJobProgress?.((event) => {
        const { event: _event, ...job } = event;
        // Write the shared job cache key; both the proxy speed-test page and
        // the environment batch bar read this key, so one SSE handler keeps
        // both pages live (t094 AC-005/AC-007).
        queryClient.setQueryData<ProxyProbeJob>(
          probeJobKeys.detail(job.job_id),
          job,
        );
        invalidateProxyLists(queryClient);
      });

    sseClient.start();

    return () => {
      unsubscribe();
      unsubscribePreview?.();
      unsubscribeReference?.();
      unsubscribeProbeJob?.();
      sseClient.stop();
    };
  }, [sseClient, queryClient]);
}


export const groupKeys = {
  all: ["groups"] as const,
  lists: () => [...groupKeys.all, "list"] as const,
  collection: (params: object) =>
    [...groupKeys.all, "collection", params] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...groupKeys.all, "collection"] as const,
};

export const proxyKeys = {
  all: ["proxies"] as const,
  lists: () => [...proxyKeys.all, "list"] as const,
  usedBy: (id: string) => [...proxyKeys.all, "used-by", id] as const,
  collection: (params: object) =>
    [...proxyKeys.all, "collection", params] as const,
  countries: () => [...proxyKeys.all, "countries"] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...proxyKeys.all, "collection"] as const,
};

export const fontSetKeys = {
  all: ["fontSets"] as const,
  lists: () => [...fontSetKeys.all, "list"] as const,
};

export const extensionKeys = {
  all: ["extensions"] as const,
  lists: () => [...extensionKeys.all, "list"] as const,
  usedBy: (assetId: string) => [...extensionKeys.all, "usedBy", assetId] as const,
};

export function useGroupsQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<GroupResponse[], Error> {
  return useQuery({
    queryKey: groupKeys.lists(),
    queryFn: () => client.groups.list(),
  });
}

export function useProxiesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyResponse[], Error> {
  return useQuery({
    queryKey: proxyKeys.lists(),
    queryFn: () => client.proxies.list(),
  });
}

export interface ProxiesCollectionParams {
  search?: string;
  country_code?: string;
  city?: string;
  scheme?: string;
  sort?: "default" | "name";
  page?: number;
  page_size?: number;
}

/** t076 AC-001/AC-006: bounded server-side proxy page. */
export function useProxiesCollectionQuery(
  params: ProxiesCollectionParams,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCollectionPage, Error> {
  return useQuery({
    queryKey: proxyKeys.collection(params),
    queryFn: () => client.proxies.listCollection(params),
  });
}

/** t076 AC-006: stable country -> city ranges for the linked filters. */
export function useProxyCountriesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCountryRange[], Error> {
  return useQuery({
    queryKey: proxyKeys.countries(),
    queryFn: () => client.proxies.listCountries(),
  });
}

/** t076 AC-004: used-by detail (same union as the count), fetched only
 * when the user opens it. */
export function useProxyUsedByQuery(
  proxyId: string | null | undefined,
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<ProxyUsedByResponse, Error> {
  return useQuery({
    queryKey: proxyKeys.usedBy(proxyId || ""),
    queryFn: () => client.proxies.getUsedBy(proxyId!),
    enabled: Boolean(proxyId) && (options.enabled ?? true),
  });
}

export function useFontSetsQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<FontSetListResponse, Error> {
  return useQuery({
    queryKey: fontSetKeys.lists(),
    queryFn: () => client.fontSets.list(),
  });
}

export function useExtensionsQuery(
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<ExtensionAssetListResponse, Error> {
  return useQuery({
    queryKey: extensionKeys.lists(),
    queryFn: () => client.extensions.list(),
    enabled: options.enabled ?? true,
  });
}

export function useExtensionUsedByQuery(
  assetId: string | null | undefined,
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<ExtensionUsedByResponse, Error> {
  return useQuery({
    queryKey: extensionKeys.usedBy(assetId || ""),
    queryFn: () => client.extensions.getUsedBy(assetId!),
    enabled: Boolean(assetId) && (options.enabled ?? true),
  });
}

export function useUploadExtensionMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ExtensionAssetResponse, Error, File> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file) => client.extensions.upload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.lists() });
    },
  });
}

export function useDeleteExtensionMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId) => client.extensions.remove(assetId),
    onSuccess: (_data, assetId) => {
      queryClient.invalidateQueries({ queryKey: extensionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: extensionKeys.usedBy(assetId) });
    },
  });
}

export function useCreateGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<GroupResponse, Error, GroupCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.groups.create(input, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useUpdateGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  GroupResponse,
  Error,
  { groupId: string; data: GroupUpdateRequest }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.groups.update(input.groupId, input.data, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useDeleteGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.groups.remove(input, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useReorderGroupsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<GroupResponse[], Error, { orderedIds: string[] }> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.groups.reorder({ ordered_ids: input.orderedIds }, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
    },
  });
}

export function useCreateProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProxyResponse, Error, ProxyCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.proxies.create(input, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useUpdateProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProxyResponse,
  Error,
  { proxyId: string; data: ProxyUpdateRequest }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.proxies.update(input.proxyId, input.data, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useDeleteProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.proxies.remove(input, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

/** t094: submit one server-owned probe job. The 202 receipt is written into
 * the job read-model cache immediately so the page can drive row state before
 * the first SSE snapshot arrives; the proxy lists are invalidated once so
 * fresh observations surface. */
export function useSubmitProbeJobMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProxyProbeJobAccepted, Error, ProxyProbeJobRequest> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => client.probes.createProbeJob(input),
    onSuccess: (accepted, input) => {
      const now = new Date().toISOString();
      const members: ProxyProbeJobMember[] = (input.proxy_ids ?? []).map(
        (proxyId) => ({ proxy_id: proxyId, state: "pending" }),
      );
      queryClient.setQueryData<ProxyProbeJob>(
        probeJobKeys.detail(accepted.job_id),
        {
          job_id: accepted.job_id,
          state: accepted.state,
          total: accepted.total,
          completed: accepted.completed,
          failed: accepted.failed,
          processed: accepted.completed + accepted.failed,
          created_at: now,
          updated_at: now,
          members,
        },
      );
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

/** t094: read one probe job. Pre-seeded from the submit receipt, then kept
 * current by `probe_job_progress` SSE events written directly to this cache. */
export function useProbeJobQuery(
  jobId: string | null | undefined,
  enabled: boolean = true,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyProbeJob, Error> {
  return useQuery({
    queryKey: probeJobKeys.detail(jobId || ""),
    queryFn: () => client.probes.getProbeJob(jobId!),
    enabled: Boolean(jobId) && enabled,
    staleTime: 30_000,
  });
}

/** t094 AC-007: read model for a server-driven environment batch job.
 * Uses the same cache key as proxy probe jobs so the single SSE
 * `probe_job_progress` handler keeps both pages live (no key divergence). */
export function useProfileBatchJobQuery(
  jobId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyProbeJob, Error> {
  return useQuery({
    queryKey: probeJobKeys.detail(jobId || ""),
    queryFn: () => client.profileBatchJobs.get(jobId!),
    enabled: Boolean(jobId),
    staleTime: 30_000,
  });
}
