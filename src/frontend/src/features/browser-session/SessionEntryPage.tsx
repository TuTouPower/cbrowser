import { Link } from "react-router";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { Banner, Button, ConfigPendingNotice, EmptyState, StatusBadge } from "../../shared/ui";
import {
  useAllProfilesCollectionQuery,
  useApplyConfigRestart,
} from "../profiles/useProfilesQuery";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

export function SessionEntryPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const profilesQuery = useAllProfilesCollectionQuery(
    { status: "running_exact", page_size: 100 },
    client,
  );
  const profiles = profilesQuery.data ?? [];
  const profilesPending = profilesQuery.isPending;
  const profilesError = profilesQuery.isError
    ? (profilesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const apply = useApplyConfigRestart(client);

  const running = profiles.filter(
    (profile) => profile.runtime?.observed_state === "running",
  );
  const loading = profilesPending;
  const handleRetry = () => {
    if (profilesQuery.isError) void profilesQuery.refetch();
  };

  const blockingError = profilesError;

  return (
    <div data-testid={SESS_ENTRY_PAGE} className="flex flex-col gap-lg">
      <h1 className="font-ui text-headline-md text-on-surface">
        {t("sessEntryTitle")}
      </h1>
      {blockingError ? (
        <Banner tone="danger" testId="sess-entry-error">
          <span>{blockingError}</span>
          <Button size="sm" data-testid="sess-entry-retry" onClick={handleRetry}>
            {t("retryAction")}
          </Button>
        </Banner>
      ) : (
        <>
          {loading ? (
            <p className="font-ui text-body-md text-on-surface-muted">
              {t("loading")}
            </p>
          ) : running.length === 0 ? (
            <EmptyState
              title={t("sessEntryEmpty")}
              description={t("sessEntryHint")}
            />
          ) : (
            <ul data-testid={SESS_ENTRY_LIST} className="flex flex-col gap-sm">
              {running.map((profile) => (
                <li
                  key={profile.id}
                  className="flex flex-wrap items-center justify-between gap-md rounded-md border border-outline bg-surface px-md py-sm"
                >
                  <Link
                    data-testid={SESS_ENTRY_LINK}
                    to={`/session/${encodeURIComponent(profile.id)}`}
                    className="flex flex-1 items-center justify-between gap-md font-ui text-body-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  >
                    <span className="truncate">{profile.name}</span>
                    <StatusBadge tone="running" label={t("statusRunning")} />
                  </Link>
                  <ConfigPendingNotice
                    pending={Boolean(profile.runtime?.config_pending)}
                    isPending={apply.scope(profile.id).isPending}
                    variant="inline"
                    testId={`sess-entry-config-pending-${profile.id}`}
                    applyTestId={`sess-entry-config-apply-${profile.id}`}
                    onApply={() => apply.apply(profile.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
