import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import {
  useProfilesQuery,
  useProfilesCollectionQuery,
  useProfileRuntimeQuery,
  useCreateProfileMutation,
  useUpdateProfileMutation,
  useDeleteProfileMutation,
  useDuplicateProfileMutation,
  useSetDesiredStateMutation,
  useProfileEventsSync,
  profileKeys,
  groupKeys,
  probeJobKeys,
  proxyKeys,
  extensionKeys,
} from "./useProfilesQuery";
import { ApiClient } from "../../shared/api/client";
import {
  DEFAULT_PROFILE_CREATE_VALUES,
  type ProfileCollectionItem,
  type ProfileCollectionPage,
  type ProfileRuntimeProjection,
  type ProfileRuntimeResponse,
} from "../../shared/api/types";
import {
  ProfileEventsClient,
  type ProfileRuntimeEvent,
  type ReferenceChangedEvent,
} from "../../shared/api/sse";

describe("useProfilesQuery & SSE Sync", () => {
  let queryClient: QueryClient;
  let mockApiClient: ApiClient;
  let mockSseClient: ProfileEventsClient;
  let sseCallback: ((event: ProfileRuntimeEvent) => void) | null = null;
  let listCallCount = 0;
  let runtimeCallCount = 0;
  let collectionCallCount = 0;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    mockApiClient = new ApiClient();
    listCallCount = 0;
    runtimeCallCount = 0;
    collectionCallCount = 0;
    mockApiClient.profiles.list = async () => {
      listCallCount += 1;
      return [
      {
        id: "p1",
        name: "Profile 1",
        display_number: 1,
        fingerprint_seed: 100,
        screen_width: 1920,
        screen_height: 1080,
        color_scheme: "light",
        include_cjk_fonts: false,
        geoip: false,
        clipboard_sync: false,
        allow_extensions: false,
        extension_ids: [],
        set_google_default: true,
        capture_preview: true,
        restore_session: true,
        mute_audio: false,
        user_data_dir: "/data/p1",
        sort_order: 0,
        current_config_version: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    };
    mockApiClient.profiles.getRuntimeAlerts = async () => {
      return { entries: [] };
    };
    mockApiClient.profiles.listCollection = async () => {
      collectionCallCount += 1;
      return { items: [], total: 0, page: 1, page_size: 50 };
    };
    mockApiClient.profiles.getRuntime = async (id: string) => {
      runtimeCallCount += 1;
      return {
        profile_id: id,
        display_number: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: null,
        config_version: 1,
        config_pending: false,
        state_revision: 1,
        failure_count: 0,
        restart_blocked: false,
        last_exit_event_id: null,
        updated_at: "2026-01-01T00:00:00Z",
      };
    };
    mockApiClient.profiles.create = async (req) => ({
      id: "p2",
      name: req.name,
      display_number: 1,
      fingerprint_seed: 200,
      screen_width: 1920,
      screen_height: 1080,
      color_scheme: "light",
      include_cjk_fonts: false,
      geoip: false,
      clipboard_sync: false,
      allow_extensions: false,
      extension_ids: [],
      set_google_default: true,
      capture_preview: true,
      restore_session: true,
      mute_audio: false,
      user_data_dir: "/data/p2",
      sort_order: 0,
      current_config_version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mockApiClient.profiles.setDesiredState = async (id, state) => ({
      profile_id: id,
      display_number: 1,
      desired_state: state,
      observed_state: "starting",
      runtime_instance_id: null,
      config_version: 1,
      config_pending: false,
      state_revision: 2,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      updated_at: "2026-01-01T00:00:00Z",
    });

    mockSseClient = new ProfileEventsClient();
    mockSseClient.onEvent = (cb) => {
      sseCallback = cb;
      return () => {
        sseCallback = null;
      };
    };
    mockSseClient.start = () => {};
    mockSseClient.close = () => {};
  });

  const createWrapper = () => {
    return ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);
  };

  // t098: a collection row's runtime projection fixture.
  const makeProjection = (
    overrides: Partial<ProfileRuntimeProjection> = {},
  ): ProfileRuntimeProjection => ({
    desired_state: "stopped",
    observed_state: "stopped",
    config_version: 1,
    config_pending: false,
    state_revision: 1,
    runtime_instance_id: null,
    failure_count: 0,
    restart_blocked: false,
    last_started_at: null,
    last_stopped_at: null,
    preview_captured_at: null,
    last_coordinator_error: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  });

  const makeCollectionItem = (
    overrides: Partial<ProfileCollectionItem> = {},
  ): ProfileCollectionItem =>
    ({
      id: "p1",
      name: "Profile 1",
      display_number: 1,
      fingerprint_seed: 100,
      user_data_dir: "/data/p1",
      current_config_version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      capture_preview: true,
      runtime: makeProjection(),
      ...overrides,
    }) as ProfileCollectionItem;

  const seedCollection = (
    items: ProfileCollectionItem[],
    params: object = {},
  ) => {
    queryClient.setQueryData<ProfileCollectionPage>(
      profileKeys.collection(params),
      { items, total: items.length, page: 1, page_size: 50 },
    );
  };

  const collectionRow = (params: object = {}) =>
    queryClient.getQueryData<ProfileCollectionPage>(
      profileKeys.collection(params),
    )?.items?.[0];

  it("fetches profile list using TanStack Query", async () => {
    const { result } = renderHook(() => useProfilesQuery(mockApiClient), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.name).toBe("Profile 1");
  });

  it("creates a profile and invalidates the profiles cache", async () => {
    const { result } = renderHook(
      () => ({
        list: useProfilesQuery(mockApiClient),
        create: useCreateProfileMutation(mockApiClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    await act(async () => {
      await result.current.create.mutateAsync({
        ...DEFAULT_PROFILE_CREATE_VALUES,
        name: "Created via Mutation",
      });
    });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    await waitFor(() => expect(listCallCount).toBeGreaterThanOrEqual(2));
    expect(
      queryClient.getQueryData<Array<{ name: string }>>(profileKeys.lists()),
    ).toBeDefined();
  });

  it("updates runtime query cache dynamically when SSE event arrives", async () => {
    const { result } = renderHook(
      () => ({
        runtime: useProfileRuntimeQuery("p1", mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.runtime.isSuccess).toBe(true));
    expect(result.current.runtime.data?.observed_state).toBe("stopped");

    // Simulate SSE push
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          config_pending: false,
          state_revision: 2,
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-999",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // Verify cache updated immediately
    const cachedRuntime = queryClient.getQueryData(profileKeys.runtime("p1"));
    expect(cachedRuntime).toMatchObject({
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-999",
    });
  });

  // t076 AC-003 replaces the old refetch-on-SSE contract: an SSE event
  // updates the cached runtime in place and must NOT trigger a refetch
  // of the runtime query or the profile lists. The previous test
  // ("invalidates the runtime query so an SSE event refetches
  // authoritative state") asserted the removed behavior and is deleted
  // wholesale; this test pins the new one.
  it("applies an SSE event in place without refetching runtime or lists", async () => {
    const { result } = renderHook(
      () => ({
        runtime: useProfileRuntimeQuery("p1", mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.runtime.isSuccess).toBe(true));
    const callsBeforeEvent = runtimeCallCount;

    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          config_pending: false,
          state_revision: 2,
          desired_state: "running",
          observed_state: "starting",
          runtime_instance_id: "inst-42",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // The event's state is visible from the cache immediately, with no
    // additional fetch: the authoritative state is the event itself.
    const cachedRuntime = queryClient.getQueryData(profileKeys.runtime("p1"));
    expect(cachedRuntime).toMatchObject({
      observed_state: "starting",
      runtime_instance_id: "inst-42",
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(runtimeCallCount).toBe(callsBeforeEvent);
  });

  it("does not fabricate runtime state for a profile without cached runtime data", async () => {
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });

    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "uncached",
          config_version: 1,
          config_pending: false,
          state_revision: 1,
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-1",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // The sync never synthesizes a runtime entry from an event: a
    // profile with no cached runtime stays uncached even when its
    // event carries a config version.
    expect(queryClient.getQueryData(profileKeys.runtime("uncached"))).toBeUndefined();
  });

  // t098 (ex-t076 review f001): list/entry pages read the collection
  // rows, so the per-profile runtime cache is empty on first open —
  // the event must still reach the row's projection (fenced by the
  // row's own state_revision), without synthesizing a runtime entry.
  it("updates the collection row from an SSE event when no per-profile runtime cache exists", async () => {
    seedCollection([makeCollectionItem()]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_started_at: "2026-01-02T10:00:00Z",
        last_stopped_at: null,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(collectionRow()?.runtime?.observed_state).toBe("running");
    expect(collectionRow()?.runtime?.runtime_instance_id).toBe("inst-1");
    expect(collectionRow()?.runtime?.last_started_at).toBe(
      "2026-01-02T10:00:00Z",
    );
    expect(collectionRow()?.runtime?.state_revision).toBe(2);
    // No runtime entry is synthesized from the event.
    expect(queryClient.getQueryData(profileKeys.runtime("p1"))).toBeUndefined();

    // The row fences stale events too: an older revision must not
    // overwrite the newer row state — even when it carries a HIGHER
    // config version (the revision is the single shared fence).
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 9,
        config_pending: false,
        state_revision: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-0",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:01:00Z",
      });
    });
    expect(collectionRow()?.runtime?.observed_state).toBe("running");
  });

  // t076 review f002: a time-only event (same states, new start time)
  // is a real change — the old change check ignored the timestamps
  // and dropped it, so rows kept showing the previous start time.
  it("copies start/stop timestamps from an SSE event into the runtime and collection caches", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      config_pending: false,
      state_revision: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      last_started_at: "2026-01-01T10:00:00Z",
      last_stopped_at: null,
      search_defaults: null,
      updated_at: "2026-01-01T10:00:00Z",
    });
    seedCollection([
      makeCollectionItem({
        runtime: makeProjection({
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-1",
          last_started_at: "2026-01-01T10:00:00Z",
        }),
      }),
    ]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_started_at: "2026-01-02T10:00:00Z",
        last_stopped_at: null,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.last_started_at,
    ).toBe("2026-01-02T10:00:00Z");
    expect(collectionRow()?.runtime?.last_started_at).toBe(
      "2026-01-02T10:00:00Z",
    );
  });

  // t098 (ex-t076 review f002): a preview capture moves the
  // collection row's projection the list renders, under the same
  // no-regression fence.
  it("updates the collection row preview time from a preview event without a per-profile runtime cache", async () => {
    let previewCallback:
      | ((event: {
          profile_id: string;
          captured_at: string;
        }) => void)
      | null = null;
    mockSseClient.onPreviewEvent = (cb) => {
      previewCallback = cb as typeof previewCallback;
      return () => {
        previewCallback = null;
      };
    };
    seedCollection([makeCollectionItem()]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const previewAt = () => collectionRow()?.runtime?.preview_captured_at;

    act(() => {
      previewCallback?.({
        profile_id: "p1",
        captured_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(previewAt()).toBe("2026-01-02T10:00:00Z");

    // An older capture must not move the time backwards.
    act(() => {
      previewCallback?.({
        profile_id: "p1",
        captured_at: "2026-01-01T09:00:00Z",
      });
    });
    expect(previewAt()).toBe("2026-01-02T10:00:00Z");
  });

  // t098 (ex-t076 review test f003): hook-level disconnect/reconnect
  // — the sync unmounts (SSE stops) and remounts (SSE restarts), then
  // a replayed event must bring the collection row to the latest
  // state without triggering a full collection refetch.
  it("recovers the collection across an SSE disconnect and reconnect without refetching", async () => {
    mockApiClient.profiles.listCollection = async () => {
      collectionCallCount += 1;
      return {
        items: [makeCollectionItem()],
        total: 1,
        page: 1,
        page_size: 50,
      };
    };
    const { result, unmount } = renderHook(
      () => ({
        collection: useProfilesCollectionQuery({}, mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() =>
      expect(result.current.collection.isSuccess).toBe(true),
    );
    expect(collectionCallCount).toBe(1);

    // Disconnect: unmounting the hook stops the SSE client and drops
    // the subscription; the QueryClient survives.
    unmount();

    // Reconnect: a fresh mount re-subscribes, restarts the client and
    // refetches the collection (the server's snapshot after
    // reconnect). The refetch is the reconnect snapshot — the
    // replayed event after it must not trigger another one.
    const second = renderHook(
      () => ({
        collection: useProfilesCollectionQuery({}, mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() =>
      expect(second.result.current.collection.data?.items?.[0]?.id).toBe(
        "p1",
      ),
    );
    const callsAfterReconnect = collectionCallCount;

    // The server replays the missed state change after reconnect.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-9",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(collectionRow()?.runtime?.observed_state).toBe("running");
    expect(collectionRow()?.runtime?.runtime_instance_id).toBe("inst-9");
    expect(collectionCallCount).toBe(callsAfterReconnect);
  });

  it("merges search_defaults from runtime events into the cached runtime", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      config_pending: false,
      state_revision: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });

    const status = {
      state: "failed" as const,
      error_kind: "timeout",
      runtime_instance_id: "inst-1",
      request_id: null,
      updated_at: "2026-11-04T00:01:00Z",
    };
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          config_pending: false,
          state_revision: 2,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-11-04T00:01:00Z",
          search_defaults: status,
        });
      }
    });
    const merged = queryClient.getQueryData<ProfileRuntimeResponse>(
      profileKeys.runtime("p1"),
    );
    expect(merged?.search_defaults).toEqual(status);

    // An event without the field leaves the cached status untouched.
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          config_pending: false,
          state_revision: 3,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-11-04T00:02:00Z",
        });
      }
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"))
        ?.search_defaults,
    ).toEqual(status);
  });

  // t098 AC-002: revision fencing — state_revision is bumped on
  // every runtime write, so a late event from an older write (an old
  // bound config version, or a superseded instance at the same
  // version) always carries a lower revision and must not overwrite
  // newer cached state; a byte-identical replay must not touch the
  // cache at all. A genuinely newer write wins even when its config
  // version went DOWN (a rollback is a later write, not a stale one).
  it("ignores stale-revision, stale-instance and duplicate SSE events", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-new",
      config_version: 3,
      config_pending: false,
      state_revision: 5,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });
    const cached = () =>
      queryClient.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"));

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-old",
        config_version: 2,
        config_pending: false,
        state_revision: 4,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(cached()?.observed_state).toBe("running");
    expect(cached()?.runtime_instance_id).toBe("inst-new");

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-other",
        config_version: 3,
        config_pending: false,
        state_revision: 4,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(cached()?.observed_state).toBe("running");
    expect(cached()?.runtime_instance_id).toBe("inst-new");

    const before = cached();
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-new",
        config_version: 3,
        config_pending: false,
        state_revision: 5,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:00:00Z",
      });
    });
    expect(cached()).toBe(before);

    // A later write at a LOWER config version (rollback) carries a
    // higher revision and does apply.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-new",
        config_version: 2,
        config_pending: false,
        state_revision: 6,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:02:00Z",
      });
    });
    expect(cached()?.observed_state).toBe("stopped");
    expect(cached()?.config_version).toBe(2);
    expect(cached()?.state_revision).toBe(6);
  });

  // t098 (ex-t076 review f009): the two caches usually disagree on
  // revision -- a collection page is refetched on focus/remount while
  // the per-profile runtime cache is only refetched on a detail
  // visit. Each cache must fence by its OWN revision: a late rev-1
  // event must not roll the rev-2 row back, even when the rev-1
  // runtime cache lets it through.
  it("fences each cache by its own revision when the caches disagree (runtime rev1, row rev2)", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      config_pending: false,
      state_revision: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    seedCollection([
      makeCollectionItem({
        runtime: makeProjection({
          desired_state: "running",
          observed_state: "running",
          config_version: 2,
          config_pending: false,
          state_revision: 2,
          runtime_instance_id: "inst-2",
          last_started_at: "2026-11-04T00:00:00Z",
        }),
      }),
    ]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    // A replayed/late rev-1 event arrives after the row already
    // moved to rev 2.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    // The rev-1 runtime cache's own fence passes (equal revision,
    // newer timestamps), so it moves -- but the rev-2 row must not be
    // rolled back to the old event.
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.observed_state,
    ).toBe("stopped");
    expect(collectionRow()?.runtime?.observed_state).toBe("running");
    expect(collectionRow()?.runtime?.state_revision).toBe(2);
    expect(collectionRow()?.runtime?.runtime_instance_id).toBe("inst-2");
  });

  // Opposite direction: a stale rev-1 event passes the rev-1 row's
  // fence but must not touch the rev-2 runtime cache.
  it("fences each cache by its own revision when the caches disagree (runtime rev2, row rev1)", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-2",
      config_version: 2,
      config_pending: false,
      state_revision: 2,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    seedCollection([
      makeCollectionItem({
        runtime: makeProjection({
          desired_state: "running",
          observed_state: "running",
          config_version: 1,
          config_pending: false,
          state_revision: 1,
          runtime_instance_id: "inst-1",
          last_started_at: "2026-11-04T00:00:00Z",
        }),
      }),
    ]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_stopped_at: "2026-11-04T00:01:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.observed_state,
    ).toBe("running");
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.state_revision,
    ).toBe(2);
    expect(collectionRow()?.runtime?.observed_state).toBe("stopped");
    expect(collectionRow()?.runtime?.last_stopped_at).toBe(
      "2026-11-04T00:01:00Z",
    );
  });

  // t098 (ex-t076 review test f010): an event without
  // config_version/state_revision predates the fences and is treated
  // as current for both caches via the legacy version+instance
  // fallback. The wire parser casts raw JSON
  // (`parseProfileRuntimeEvent` returns `raw as ProfileRuntimeEvent`),
  // so a fence-less event is a real runtime input even though the
  // generated type marks the fields required -- the cast below
  // simulates exactly that wire shape. The test pins the fallback
  // branches: the fence must let the event through, and the merge
  // must keep each cache's own version and revision instead of
  // writing undefined into them.
  it("treats a fence-less SSE event as current for both caches", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-2",
      config_version: 2,
      config_pending: false,
      state_revision: 7,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    seedCollection([
      makeCollectionItem({
        runtime: makeProjection({
          desired_state: "running",
          observed_state: "running",
          config_version: 2,
          config_pending: false,
          state_revision: 7,
          runtime_instance_id: "inst-2",
          last_started_at: "2026-11-04T00:00:00Z",
        }),
      }),
    ]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-2",
        config_pending: false,
        failure_count: 0,
        restart_blocked: false,
        last_stopped_at: "2026-11-04T00:01:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      } as ProfileRuntimeEvent);
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      ),
    ).toMatchObject({
      observed_state: "stopped",
      desired_state: "stopped",
      runtime_instance_id: "inst-2",
      config_version: 2,
      config_pending: false,
      state_revision: 7,
      last_stopped_at: "2026-11-04T00:01:00Z",
    });
    expect(collectionRow()?.runtime).toMatchObject({
      observed_state: "stopped",
      desired_state: "stopped",
      runtime_instance_id: "inst-2",
      config_version: 2,
      config_pending: false,
      state_revision: 7,
      last_stopped_at: "2026-11-04T00:01:00Z",
    });
  });


  it("invalidates group and profile lists on a groups_changed event (t056 A31)", async () => {
    let referenceCallback: ((event: ReferenceChangedEvent) => void) | null =
      null;
    mockSseClient.onReferenceEvent = (cb) => {
      referenceCallback = cb;
      return () => {
        referenceCallback = null;
      };
    };
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      referenceCallback?.({ event: "groups_changed", entity_id: "g1" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: groupKeys.lists(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.lists(),
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: proxyKeys.lists(),
    });
  });

  it("invalidates proxy and profile lists on a proxies_changed event (t056 A31)", async () => {
    let referenceCallback: ((event: ReferenceChangedEvent) => void) | null =
      null;
    mockSseClient.onReferenceEvent = (cb) => {
      referenceCallback = cb;
      return () => {
        referenceCallback = null;
      };
    };
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      referenceCallback?.({ event: "proxies_changed", entity_id: null });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: proxyKeys.lists(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.lists(),
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: groupKeys.lists(),
    });
  });

  it("writes the shared probe-job cache key so env batch progress stays live (t094)", () => {
    let cb: ((event: any) => void) | null = null;
    mockSseClient.onProbeJobProgress = (fn) => {
      cb = fn as any;
      return () => {
        cb = null;
      };
    };
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const job = {
      event: "probe_job_progress",
      job_id: "job-shared",
      state: "running",
      total: 3,
      completed: 2,
      failed: 0,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      members: [],
    };
    act(() => {
      cb?.(job);
    });
    expect(queryClient.getQueryData(probeJobKeys.detail("job-shared"))).toMatchObject({
      job_id: "job-shared",
      completed: 2,
    });
  });
  // t098 AC-003: a member row whose state crosses the page's status
  // filter boundary must not be merged in place -- the page is
  // invalidated so the server reconverges membership and total.
  it("invalidates a status-filtered page when a member crosses the filter boundary", async () => {
    seedCollection(
      [
        makeCollectionItem({
          runtime: makeProjection({
            desired_state: "running",
            observed_state: "running",
            state_revision: 3,
          }),
        }),
      ],
      { status: "running_exact" },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 4,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: null,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running_exact" }),
    });
    // The row was NOT merged in place (still shows the pre-event
    // state until the refetch lands).
    expect(
      collectionRow({ status: "running_exact" })?.runtime?.observed_state,
    ).toBe("running");
  });

  // t098 AC-003: a non-member whose new state enters a filtered
  // page's bucket invalidates that page (the row may need to enter);
  // a state that stays outside the bucket does nothing.
  it("invalidates a status-filtered page when a non-member enters its bucket only", async () => {
    seedCollection([], { status: "running_exact" });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p-other",
        config_version: 1,
        config_pending: false,
        state_revision: 1,
        desired_state: "running",
        observed_state: "starting",
        runtime_instance_id: "inst-x",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running_exact" }),
    });
    act(() => {
      sseCallback?.({
        profile_id: "p-other",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-x",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:01:00Z",
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running_exact" }),
    });
  });

  // t098 AC-003: a late event for a profile that already left the
  // page (e.g. deleted) must not resurrect a row, and must not
  // invalidate an unfiltered page either.
  it("never resurrects a row for an off-page profile on an unfiltered page", async () => {
    seedCollection([makeCollectionItem()]);
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p-deleted",
        config_version: 1,
        config_pending: false,
        state_revision: 9,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-ghost",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    const page = queryClient.getQueryData<ProfileCollectionPage>(
      profileKeys.collection({}),
    );
    expect(page?.items).toHaveLength(1);
    expect(page?.items?.[0]?.id).toBe("p1");
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.collection({}),
    });
  });

  // t098 AC-002: an operation result merges into the collection row
  // under the same revision fence.
  it("merges a setDesiredState result into the collection row", async () => {
    seedCollection([makeCollectionItem()]);
    const { result } = renderHook(
      () => ({
        setState: useSetDesiredStateMutation(mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await act(async () => {
      await result.current.setState.mutateAsync({
        id: "p1",
        state: "running",
      });
    });
    expect(collectionRow()?.runtime?.observed_state).toBe("starting");
    expect(collectionRow()?.runtime?.state_revision).toBe(2);
  });

  // t098 AC-003: the global coordinator-error alerts are invalidated
  // exactly when an event changes a profile's alert state.
  // t098 test review f001 (AC-002): the collection read itself races
  // the event stream — a page requested before an event must not roll
  // the row back when its (older) response lands after the event.
  it("a slow collection response landing after a newer event does not roll the row back", async () => {
    let resolveFetch:
      | ((page: ProfileCollectionPage) => void)
      | null = null;
    let calls = 0;
    mockApiClient.profiles.listCollection = async () => {
      calls += 1;
      if (calls === 1) {
        return {
          items: [
            makeCollectionItem({
              runtime: makeProjection({
                state_revision: 1,
                observed_state: "stopped",
              }),
            }),
          ],
          total: 1,
          page: 1,
          page_size: 50,
        };
      }
      // The refetch hangs until released, then returns the same stale
      // page it was requested with (pre-event data).
      return new Promise<ProfileCollectionPage>((resolve) => {
        resolveFetch = resolve;
      });
    };
    const { result } = renderHook(
      () => ({
        collection: useProfilesCollectionQuery({}, mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.collection.isSuccess).toBe(true));
    expect(collectionRow()?.runtime?.state_revision).toBe(1);

    // Start the refetch (in flight), then deliver a newer event.
    await act(async () => {
      void result.current.collection.refetch();
    });
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 5,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-01T00:00:00Z",
      });
    });
    expect(collectionRow()?.runtime?.observed_state).toBe("running");

    // The stale response lands now; the row must keep revision 5.
    await act(async () => {
      resolveFetch?.({
        items: [
          makeCollectionItem({
            runtime: makeProjection({
              state_revision: 1,
              observed_state: "stopped",
            }),
          }),
        ],
        total: 1,
        page: 1,
        page_size: 50,
      });
    });
    await waitFor(() =>
      expect(result.current.collection.isFetching).toBe(false),
    );
    expect(collectionRow()?.runtime?.state_revision).toBe(5);
    expect(collectionRow()?.runtime?.observed_state).toBe("running");
  });

  // t098 code review f001: an event older than the runtime cache's
  // known revision is history — it must not invalidate a filtered
  // collection page for a non-member, nor the alerts model.
  it("a stale event below the runtime cache revision triggers no collection or alerts invalidation", async () => {
    seedCollection(
      [makeCollectionItem({ runtime: makeProjection({ state_revision: 1 }) })],
      { status: "running" },
    );
    queryClient.setQueryData(profileKeys.runtime("p2"), {
      profile_id: "p2",
      display_number: 2,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-2",
      config_version: 1,
      config_pending: false,
      state_revision: 9,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      updated_at: "2026-01-01T00:00:00Z",
    });
    queryClient.setQueryData(profileKeys.runtimeAlerts(), {
      entries: [
        {
          profile_id: "p2",
          display_number: 2,
          name: "Profile 2",
          last_coordinator_error: "current error",
        },
      ],
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBeUndefined();
    act(() => {
      sseCallback?.({
        profile_id: "p2",
        config_version: 1,
        config_pending: false,
        state_revision: 3,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-2",
        failure_count: 0,
        restart_blocked: false,
        last_coordinator_error: "stale error text",
        updated_at: "2026-01-01T00:00:00Z",
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("invalidates runtime alerts only when the coordinator error changes", async () => {
    queryClient.setQueryData(profileKeys.runtimeAlerts(), {
      entries: [
        { profile_id: "p1", last_coordinator_error: "boom" },
      ],
    });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_coordinator_error: "boom",
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.runtimeAlerts(),
    });
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 3,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_coordinator_error: null,
        updated_at: "2026-01-02T10:01:00Z",
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.runtimeAlerts(),
    });
  });

  // t101 AC-001: the seen-revision watermark must be fed by collection
  // rows alone when no runtime cache exists. A late event for a
  // non-member of a filtered page must not invalidate it or alerts.
  it("suppresses a late non-member event with only a collection-row watermark", async () => {
    seedCollection([makeCollectionItem({ id: "p1" })], {
      status: "running",
    });
    queryClient.setQueryData(profileKeys.runtimeAlerts(), {
      entries: [
        {
          profile_id: "p2",
          display_number: 2,
          name: "Profile 2",
          last_coordinator_error: "current error",
        },
      ],
    });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    // Initial snapshot at rev 9 for p2 (not a member of the filtered
    // page) establishes the watermark without any runtime cache.
    act(() => {
      sseCallback?.({
        profile_id: "p2",
        config_version: 1,
        config_pending: false,
        state_revision: 9,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-2",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-01T00:00:00Z",
      });
    });
    invalidateSpy.mockClear();
    // A late rev 3 snapshot must be recognized as history even though
    // p2 has no runtime cache entry.
    act(() => {
      sseCallback?.({
        profile_id: "p2",
        config_version: 1,
        config_pending: false,
        state_revision: 3,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-2",
        failure_count: 0,
        restart_blocked: false,
        last_coordinator_error: "stale error",
        updated_at: "2026-01-01T00:00:00Z",
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running" }),
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.runtimeAlerts(),
    });
  });

  // t101 AC-001: a duplicate event at the already-seen revision must be
  // suppressed for non-member pages too (no per-row dedup there). The
  // watermark aggregates every collection cache, not just the page
  // being invalidated.
  it("suppresses a duplicate non-member event at the watermark revision", async () => {
    seedCollection([
      makeCollectionItem({
        id: "p2",
        runtime: makeProjection({
          state_revision: 9,
          observed_state: "running",
          desired_state: "running",
          runtime_instance_id: "inst-2",
        }),
      }),
    ]);
    seedCollection([makeCollectionItem({ id: "p1" })], {
      status: "running",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p2",
        config_version: 1,
        config_pending: false,
        state_revision: 9,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-2",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-01T00:00:00Z",
      });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running" }),
    });
  });

  // t101 AC-002: when a history event is suppressed, a member row that
  // would cross the status-filter boundary must stay untouched instead
  // of being written back into the wrong bucket with a stale total.
  it("does not write a suppressed cross-boundary member row back into the filtered page", async () => {
    seedCollection(
      [
        makeCollectionItem({
          id: "p1",
          runtime: makeProjection({
            state_revision: 1,
            observed_state: "running",
            desired_state: "running",
          }),
        }),
      ],
      { status: "running_exact" },
    );
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      config_pending: false,
      state_revision: 9,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      updated_at: "2026-01-01T00:00:00Z",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 5,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(
      collectionRow({ status: "running_exact" })?.runtime?.observed_state,
    ).toBe("running");
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running_exact" }),
    });
  });

  // t101 review f001 regression: a fresh event must not be mistaken for
  // a replay of itself just because the runtime cache is about to be
  // written with it. With a runtime cache present, a real state change
  // still invalidates the filtered page and the alerts model.
  it("invalidates a filtered page and alerts for a fresh event with a runtime cache present", async () => {
    seedCollection(
      [
        makeCollectionItem({
          id: "p1",
          runtime: makeProjection({
            state_revision: 1,
            observed_state: "running",
            desired_state: "running",
            runtime_instance_id: "inst-1",
            last_coordinator_error: "boom",
          }),
        }),
      ],
      { status: "running_exact" },
    );
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      config_pending: false,
      state_revision: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      preview_captured_at: null,
      last_started_at: null,
      last_stopped_at: null,
      last_coordinator_error: "boom",
      updated_at: "2026-01-01T00:00:00Z",
    });
    queryClient.setQueryData(profileKeys.runtimeAlerts(), {
      entries: [
        {
          profile_id: "p1",
          display_number: 1,
          name: "Profile 1",
          last_coordinator_error: "boom",
        },
      ],
    });
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        config_pending: false,
        state_revision: 2,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_coordinator_error: null,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.collection({ status: "running_exact" }),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.runtimeAlerts(),
    });
  });

  it("invalidates extensionKeys on create, update, delete, and duplicate profile mutations (t104)", async () => {
    const sampleProfile = {
      id: "p1",
      name: "Profile 1",
      display_number: 1,
      fingerprint_seed: 100,
      screen_width: 1920,
      screen_height: 1080,
      color_scheme: "light" as const,
      include_cjk_fonts: false,
      geoip: false,
      clipboard_sync: false,
      allow_extensions: true,
      extension_ids: [],
      set_google_default: true,
      capture_preview: true,
      restore_session: true,
      mute_audio: false,
      user_data_dir: "/data/p1",
      sort_order: 0,
      current_config_version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    mockApiClient.profiles.create = vi.fn(async () => sampleProfile);
    mockApiClient.profiles.update = vi.fn(async () => sampleProfile);
    mockApiClient.profiles.delete = vi.fn(async () => undefined);
    mockApiClient.profiles.duplicate = vi.fn(async () => ({ ...sampleProfile, id: "p2" }));

    const wrapper = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const createHook = renderHook(() => useCreateProfileMutation(mockApiClient), { wrapper });
    const updateHook = renderHook(() => useUpdateProfileMutation(mockApiClient), { wrapper });
    const deleteHook = renderHook(() => useDeleteProfileMutation(mockApiClient), { wrapper });
    const dupHook = renderHook(() => useDuplicateProfileMutation(mockApiClient), { wrapper });

    await act(async () => {
      await createHook.result.current.mutateAsync({ ...DEFAULT_PROFILE_CREATE_VALUES, name: "New" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: extensionKeys.all });

    invalidateSpy.mockClear();
    await act(async () => {
      await updateHook.result.current.mutateAsync({ id: "p1", data: { allow_extensions: false } });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: extensionKeys.all });

    invalidateSpy.mockClear();
    await act(async () => {
      await deleteHook.result.current.mutateAsync("p1");
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: extensionKeys.all });

    invalidateSpy.mockClear();
    await act(async () => {
      await dupHook.result.current.mutateAsync({ id: "p1", includeBrowserState: false });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: extensionKeys.all });
  });
});

