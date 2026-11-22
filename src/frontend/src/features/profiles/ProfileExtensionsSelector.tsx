import { useRef, useState } from "react";
import { ArrowDown, ArrowUp, Puzzle, Upload, X } from "lucide-react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { ExtensionAssetResponse } from "../../shared/api/types";
import { Banner, Button } from "../../shared/ui";
import {
  useExtensionsQuery,
  useUploadExtensionMutation,
} from "./useProfilesQuery";

export function ProfileExtensionsSelector({
  extensionIds,
  onChange,
}: {
  extensionIds: string[];
  onChange: (nextIds: string[]) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, isError } = useExtensionsQuery(client);
  const uploadMutation = useUploadExtensionMutation(client);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const items = data?.items ?? [];
  const byId = new Map<string, ExtensionAssetResponse>(
    items.map((item) => [item.id, item]),
  );
  const selectedChromiumIds = new Set(
    extensionIds
      .map((id) => byId.get(id)?.chromium_id)
      .filter((cid): cid is string => Boolean(cid)),
  );

  const move = (index: number, delta: -1 | 1) => {
    const target = index + delta;
    if (target < 0 || target >= extensionIds.length) return;
    const next = [...extensionIds];
    const [picked] = next.splice(index, 1);
    if (picked !== undefined) {
      next.splice(target, 0, picked);
    }
    onChange(next);
  };

  const removeAt = (index: number) => {
    const next = [...extensionIds];
    next.splice(index, 1);
    onChange(next);
  };

  const attach = (asset: ExtensionAssetResponse) => {
    if (extensionIds.includes(asset.id)) return;
    if (selectedChromiumIds.has(asset.chromium_id)) return;
    onChange([...extensionIds, asset.id]);
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadError(null);
    try {
      const asset = await uploadMutation.mutateAsync(file);
      if (!extensionIds.includes(asset.id)) {
        const filtered = extensionIds.filter(
          (id) => byId.get(id)?.chromium_id !== asset.chromium_id,
        );
        onChange([...filtered, asset.id]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setUploadError(t("extensionsUploadFailed", { error: msg }));
    }
  };

  const available = items.filter((asset) => !extensionIds.includes(asset.id));

  return (
    <div
      data-testid="profile-form-extensions-selector"
      className="flex flex-col gap-md"
    >
      <Banner tone="warning" testId="profile-form-extensions-warning">
        {t("formExtensionsPrivacyNotice")}
      </Banner>

      <div className="flex flex-wrap items-center justify-between gap-sm">
        <span className="font-ui text-label-sm text-on-surface">
          {t("formExtensionsSelectedTitle")}
        </span>
        <div>
          <input
            ref={fileRef}
            data-testid="profile-form-extension-file-input"
            type="file"
            accept=".crx,.zip"
            className="hidden"
            onChange={handleUpload}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-testid="profile-form-upload-extension"
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
      </div>

      {uploadError && (
        <Banner
          tone="danger"
          testId="profile-form-extension-upload-error"
          onDismiss={() => setUploadError(null)}
        >
          {uploadError}
        </Banner>
      )}

      {isError && (
        <Banner tone="danger" testId="profile-form-extensions-load-error">
          {t("extensionsLoadFailed")}
        </Banner>
      )}

      {extensionIds.length === 0 ? (
        <div
          data-testid="profile-form-free-extensions-hint"
          className="rounded-md border border-outline bg-surface-subtle px-md py-sm font-ui text-body-sm text-on-surface-muted"
        >
          {t("formExtensionsFreeModeHint")}
        </div>
      ) : (
        <ul
          data-testid="profile-form-selected-extensions"
          className="flex flex-col gap-xs"
        >
          {extensionIds.map((assetId, idx) => {
            const asset = byId.get(assetId);
            return (
              <li
                key={assetId}
                data-testid={`profile-selected-ext-${assetId}`}
                className="flex items-center justify-between gap-sm rounded-md border border-outline bg-surface-subtle px-md py-sm"
              >
                <div className="flex flex-1 items-center gap-sm overflow-hidden">
                  {asset?.has_icon && asset.icon_url ? (
                    <img
                      src={asset.icon_url}
                      alt=""
                      className="size-(--component-icon-md-size) shrink-0 rounded-sm object-contain"
                    />
                  ) : (
                    <Puzzle
                      aria-hidden="true"
                      className="size-(--component-icon-md-size) shrink-0 text-on-surface-muted"
                    />
                  )}
                  <div className="flex-1 overflow-hidden">
                    <div className="truncate font-ui text-body-sm text-on-surface">
                      {asset ? `${asset.name} v${asset.version}` : assetId}
                    </div>
                    <div className="truncate font-mono text-mono-md text-on-surface-muted">
                      {asset ? asset.chromium_id : assetId}
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-xs">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={t("formExtensionsMoveUp")}
                    data-testid={`ext-move-up-${assetId}`}
                    disabled={idx === 0}
                    onClick={() => move(idx, -1)}
                  >
                    <ArrowUp
                      aria-hidden="true"
                      className="size-(--component-icon-sm-size)"
                    />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={t("formExtensionsMoveDown")}
                    data-testid={`ext-move-down-${assetId}`}
                    disabled={idx === extensionIds.length - 1}
                    onClick={() => move(idx, 1)}
                  >
                    <ArrowDown
                      aria-hidden="true"
                      className="size-(--component-icon-sm-size)"
                    />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={t("formExtensionsRemove")}
                    data-testid={`ext-remove-${assetId}`}
                    onClick={() => removeAt(idx)}
                  >
                    <X
                      aria-hidden="true"
                      className="size-(--component-icon-sm-size)"
                    />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {available.length > 0 && (
        <div className="flex flex-col gap-xs">
          <span className="font-ui text-label-sm text-on-surface-muted">
            {t("formExtensionsAvailableTitle")}
          </span>
          <ul
            data-testid="profile-form-available-extensions"
            className="flex flex-col gap-xs"
          >
            {available.map((asset) => {
              const cidConflict = selectedChromiumIds.has(asset.chromium_id);
              return (
                <li
                  key={asset.id}
                  data-testid={`profile-available-ext-${asset.id}`}
                  className="flex items-center justify-between gap-sm rounded-md border border-outline-subtle bg-surface px-md py-sm"
                >
                  <div className="flex flex-1 items-center gap-sm overflow-hidden">
                    {asset.has_icon && asset.icon_url ? (
                      <img
                        src={asset.icon_url}
                        alt=""
                        className="size-(--component-icon-md-size) shrink-0 rounded-sm object-contain"
                      />
                    ) : (
                      <Puzzle
                        aria-hidden="true"
                        className="size-(--component-icon-md-size) shrink-0 text-on-surface-muted"
                      />
                    )}
                    <div className="flex-1 overflow-hidden">
                      <div className="truncate font-ui text-body-sm text-on-surface">
                        {asset.name} v{asset.version}
                      </div>
                      <div className="truncate font-mono text-mono-md text-on-surface-muted">
                        {asset.chromium_id}
                      </div>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    data-testid={`ext-attach-${asset.id}`}
                    disabled={cidConflict || !asset.integrity.ok}
                    title={
                      cidConflict ? t("formExtensionsConflictId") : undefined
                    }
                    onClick={() => attach(asset)}
                  >
                    <span>
                      {cidConflict
                        ? t("formExtensionsConflictId")
                        : t("formExtensionsAttach")}
                    </span>
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
