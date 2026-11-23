import { Banner, Button, ConfigPendingNotice } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import {
  useApplyConfigRestart,
  useProfileQuery,
  useProfileRuntimeQuery,
  useRetrySearchDefaultsMutation,
} from "./useProfilesQuery";

export function SharedProfileBanners({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: profile } = useProfileQuery(profileId, client);
  const { data: runtime } = useProfileRuntimeQuery(profileId, client);
  const retryMutation = useRetrySearchDefaultsMutation(client);
  const apply = useApplyConfigRestart(client);
  const applyScope = apply.scope(profileId);

  const searchDefaultsFailed = runtime?.search_defaults?.state === "failed";

  return (
    <div data-testid="profile-shared-banners" className="flex flex-col gap-sm">
      {searchDefaultsFailed && (
        <Banner tone="warning" testId="profile-search-defaults-failed">
          <span>{t("detailSearchDefaultsFailed")}</span>
          <Button
            size="sm"
            disabled={retryMutation.isPending}
            onClick={() => retryMutation.mutate(profileId)}
          >
            {t("detailRetrySearchDefaults")}
          </Button>
        </Banner>
      )}
      <ConfigPendingNotice
        pending={Boolean(profile && runtime?.config_pending)}
        isPending={applyScope.isPending}
        testId="profile-apply-pending"
        onApply={() => apply.apply(profileId)}
      />
      {applyScope.isError && (
        <Banner tone="danger" testId="profile-apply-error">
          {t("detailApplyError")}
        </Banner>
      )}
    </div>
  );
}
