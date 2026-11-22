import { useRef, useState } from "react";
import { Puzzle, Trash2, Upload } from "lucide-react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ExtensionAssetResponse,
} from "../../shared/api/types";
import { Banner, Button, StatusBadge } from "../../shared/ui";
import {
  useDeleteExtensionMutation,
  useExtensionsQuery,
  useExtensionUsedByQuery,
  useUploadExtensionMutation,
} from "../profiles/useProfilesQuery";

function ExtensionUsedByList({ assetId }: { assetId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data, isLoading, isError } = useExtensionUsedByQuery(assetId, client);

  if (isLoading) {
    return (
      <p className="font-ui text-body-sm text-on-surface-muted">...</p>
    );
  }
  if (isError) {
    return (
      <p className="font-ui text-body-sm text-danger">
        {t("extensionsLoadFailed")}
      </p>
    );
  }
  const entries = data?.entries ?? [];
  if (entries.length === 0) {
    return (
      <p className="font-ui text-body-sm text-on-surface-muted">
        {t("extensionsUsedBy")}: 0
      </p>
    );
  }
  return (
    <ul
      data-testid={`extension-used-by-${assetId}`}
      className="flex flex-col gap-xs rounded-sm border border-outline-subtle bg-surface-subtle p-sm font-ui text-body-sm"
    >
      {entries.map((entry) => {
        const kindLabel =
          entry.kind === "both"
            ? t("extensionsUsageKindBoth")
            : entry.kind === "bound"
              ? t("extensionsUsageKindBound")
              : t("extensionsUsageKindCurrent");
        return (
          <li
            key={entry.profile_id}
            className="flex flex-wrap items-center justify-between gap-sm"
          >
            <span className="text-on-surface">{entry.profile_name}</span>
            <span className="text-on-surface-muted">
              {kindLabel}
              {entry.observed_state ? ` (${entry.observed_state})` : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function ExtensionLibrarySection() {
  const { t } = useI18n();
  const client = useApiClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, isError } = useExtensionsQuery(client);
  const uploadMutation = useUploadExtensionMutation(client);
  const deleteMutation = useDeleteExtensionMutation(client);
  const [actionError, setActionError] = useState<string | null>(null);
  const [expandedAssetId, setExpandedAssetId] = useState<string | null>(null);

  const items = data?.items ?? null;

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setActionError(null);
    try {
      await uploadMutation.mutateAsync(file);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionError(t("extensionsUploadFailed", { error: msg }));
    }
  };

  const handleDelete = async (asset: ExtensionAssetResponse) => {
    setActionError(null);
    try {
      await deleteMutation.mutateAsync(asset.id);
      if (expandedAssetId === asset.id) {
        setExpandedAssetId(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionError(msg);
    }
  };

  return (
    <div data-testid="extension-library" className="flex flex-col gap-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <input
          ref={fileRef}
          data-testid="extensions-file-input"
          type="file"
          accept=".crx,.zip"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          data-testid="extensions-upload-btn"
          disabled={uploadMutation.isPending}
          onClick={() => fileRef.current?.click()}
        >
          <Upload
            aria-hidden="true"
            className="size-(--component-icon-sm-size)"
          />
          <span>
            {uploadMutation.isPending
              ? t("extensionsUploading")
              : t("extensionsUploadBtn")}
          </span>
        </Button>
      </div>

      {actionError && (
        <Banner
          tone="danger"
          testId="extensions-action-error"
          onDismiss={() => setActionError(null)}
        >
          {actionError}
        </Banner>
      )}

      {isError && (
        <Banner tone="danger" testId="extensions-load-error">
          {t("extensionsLoadFailed")}
        </Banner>
      )}

      {!isError && items?.length === 0 && (
        <p
          data-testid="extensions-empty"
          className="font-ui text-body-sm text-on-surface-muted"
        >
          {t("extensionsEmpty")}
        </p>
      )}

      {items && items.length > 0 && (
        <div className="flex flex-col gap-sm">
          {items.map((asset: ExtensionAssetResponse) => {
            const isExpanded = expandedAssetId === asset.id;
            return (
              <div
                key={asset.id}
                data-testid={`extension-card-${asset.id}`}
                className="flex flex-col gap-sm rounded-md border border-outline bg-surface p-md"
              >
                <div className="flex flex-wrap items-start justify-between gap-sm">
                  <div className="flex flex-1 items-center gap-sm overflow-hidden">
                    {asset.has_icon && asset.icon_url ? (
                      <img
                        src={asset.icon_url}
                        alt=""
                        className="size-(--component-icon-lg-size) shrink-0 rounded-sm object-contain"
                      />
                    ) : (
                      <Puzzle
                        aria-hidden="true"
                        className="size-(--component-icon-lg-size) shrink-0 text-on-surface-muted"
                      />
                    )}
                    <div className="flex-1 overflow-hidden">
                      <div className="flex flex-wrap items-center gap-xs">
                        <span className="truncate font-ui text-title-sm text-on-surface">
                          {asset.name}
                        </span>
                        <span className="font-mono text-mono-md text-on-surface-muted">
                          v{asset.version}
                        </span>
                        <StatusBadge
                          tone={asset.integrity.ok ? "running" : "error"}
                          label={
                            asset.integrity.ok
                              ? t("fontSetIntegrityOk")
                              : t("fontSetIntegrityBad")
                          }
                        />
                      </div>
                      <p className="truncate font-mono text-mono-md text-on-surface-muted">
                        {t("extensionsChromiumId")}: {asset.chromium_id} ·{" "}
                        {asset.package_format.toUpperCase()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-xs">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      data-testid={`extension-used-by-btn-${asset.id}`}
                      onClick={() =>
                        setExpandedAssetId(isExpanded ? null : asset.id)
                      }
                    >
                      <span>
                        {t("extensionsUsedBy")}: {asset.used_by_count}
                      </span>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      data-testid={`extension-delete-btn-${asset.id}`}
                      disabled={
                        asset.used_by_count > 0 || deleteMutation.isPending
                      }
                      title={
                        asset.used_by_count > 0
                          ? t("extensionsDeleteInUse", {
                              count: asset.used_by_count,
                            })
                          : t("extensionsDeleteBtn")
                      }
                      onClick={() => handleDelete(asset)}
                    >
                      <Trash2
                        aria-hidden="true"
                        className="size-(--component-icon-sm-size)"
                      />
                      <span>{t("extensionsDeleteBtn")}</span>
                    </Button>
                  </div>
                </div>
                {asset.description ? (
                  <p className="font-ui text-body-sm text-on-surface-muted">
                    {asset.description}
                  </p>
                ) : null}
                {isExpanded && <ExtensionUsedByList assetId={asset.id} />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
