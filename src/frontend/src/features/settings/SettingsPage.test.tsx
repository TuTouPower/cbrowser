import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { ProfileForm } from "../profiles/ProfileForm";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({ logout: vi.fn(async () => undefined) }),
}));

interface FontSetFixture {
  platform: string;
  set_id: string;
  source?: string | null;
  source_version?: string | null;
  integrity: { ok: boolean; problems?: string[] };
  file_count: number;
  used_by_count: number;
}

function renderPages(fontSets: FontSetFixture[] = []) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const stubClient = {
    health: { check: vi.fn(async () => undefined) },
    profiles: { create: vi.fn(async () => ({ id: "p-new" })) },
    groups: { list: vi.fn(async () => []), create: vi.fn(async () => ({})) },
    proxies: { list: vi.fn(async () => []) },
    fontSets: { list: vi.fn(async () => ({ items: fontSets, default_font_set_id: { windows: null, macos: null } })) },
    extensions: {
      list: vi.fn(async () => ({ items: [] })),
      upload: vi.fn(),
      getUsedBy: vi.fn(async () => ({ asset_id: "", entries: [] })),
      remove: vi.fn(async () => undefined),
    },
    request: vi.fn(async () => fontSets),
  } as unknown as ApiClient;
  return render(
    <I18nProvider>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <ApiClientContext.Provider value={stubClient}>
            <MemoryRouter>
              <SettingsPage />
              <ProfileForm mode="create" onSubmit={async () => {}} />
            </MemoryRouter>
          </ApiClientContext.Provider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>,
  );
}

describe("settings and profile form i18n (t035+)", () => {
  beforeEach(() => {
    localStorage.setItem("cbrowser.locale", "zh");
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("switches remaining i18n labels and placeholders", async () => {
    renderPages();

    expect(screen.getByText("控制 API")).toBeTruthy();
    expect(screen.getByText("环境名称")).toBeTruthy();
    expect(screen.getByLabelText("宽度 (px)")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("正常")).toBeTruthy());

    fireEvent.click(screen.getByText("English"));

    expect(screen.getByText("Control API")).toBeTruthy();
    expect(screen.getByText("Name")).toBeTruthy();
    expect(screen.getByLabelText("Width (px)")).toBeTruthy();
  });
});

describe("settings platform font sets (t036+)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders font set data from GET /api/v1/font-sets with human-readable font pack names", async () => {
    renderPages([
      {
        platform: "windows",
        set_id: "win11",
        source: "Windows 11 Enterprise",
        source_version: "10.0.22631",
        integrity: { ok: true },
        file_count: 346,
        used_by_count: 2,
      },
    ]);

    const card = await screen.findByTestId("font-set-windows-win11");
    expect(card).toHaveTextContent("Windows 11 Enterprise");
    expect(card).toHaveTextContent("10.0.22631");
    expect(card).toHaveTextContent("346");
    expect(card).toHaveTextContent("2");
    expect(screen.queryByTestId("font-set-integrity-bad")).not.toBeInTheDocument();
  });

  it("shows an integrity warning for a font set with problems", async () => {
    renderPages([
      {
        platform: "macos",
        set_id: "pingfang",
        source: "macOS",
        source_version: "14",
        integrity: { ok: false, problems: ["missing: PingFang.ttc"] },
        file_count: 5,
        used_by_count: 0,
      },
    ]);

    const card = await screen.findByTestId("font-set-macos-pingfang");
    expect(card).toHaveTextContent("macOS");
    expect(screen.getByTestId("font-set-integrity-bad")).toBeInTheDocument();
    expect(screen.getByTestId("font-set-problems")).toHaveTextContent(
      "missing: PingFang.ttc",
    );
  });
});

describe("settings managed extensions library (t104)", () => {
  beforeEach(() => {
    localStorage.setItem("cbrowser.locale", "en");
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders uploaded extensions, expands used-by, deletes unused, and surfaces upload errors", async () => {
    const usedId = "1".repeat(64);
    const freeId = "2".repeat(64);
    const removeFn = vi.fn(async () => undefined);
    const uploadFn = vi.fn(async () => {
      throw new Error("indeterminate_extension_identity");
    });
    const usedByFn = vi.fn(async () => ({
      asset_id: usedId,
      entries: [
        {
          profile_id: "p1",
          profile_name: "Vault Profile",
          display_number: 4,
          kind: "bound",
          observed_state: "running",
        },
      ],
    }));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const client = {
      health: { check: vi.fn(async () => undefined) },
      fontSets: {
        list: vi.fn(async () => ({
          items: [],
          default_font_set_id: { windows: null, macos: null },
        })),
      },
      extensions: {
        list: vi.fn(async () => ({
          items: [
            {
              id: usedId,
              chromium_id: "nngceckbapebfimnlniiiahkandclblb",
              name: "Bitwarden",
              version: "2026.11.0",
              manifest_version: 3,
              description: "Password manager",
              package_format: "crx3",
              identity_source: "crx3_header",
              manifest_key_sha256: "a".repeat(64),
              archive_sha256: "b".repeat(64),
              has_icon: false,
              icon_url: null,
              file_count: 10,
              total_bytes: 4096,
              integrity: { ok: true, problems: [] },
              state: "verified",
              used_by_count: 1,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
            {
              id: freeId,
              chromium_id: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
              name: "Unused Helper",
              version: "0.1.0",
              manifest_version: 3,
              description: null,
              package_format: "zip",
              identity_source: "manifest_key",
              manifest_key_sha256: "c".repeat(64),
              archive_sha256: "d".repeat(64),
              has_icon: false,
              icon_url: null,
              file_count: 2,
              total_bytes: 256,
              integrity: { ok: true, problems: [] },
              state: "verified",
              used_by_count: 0,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
        })),
        upload: uploadFn,
        getUsedBy: usedByFn,
        remove: removeFn,
      },
    } as unknown as ApiClient;

    render(
      <I18nProvider>
        <ThemeProvider>
          <QueryClientProvider client={queryClient}>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter>
                <SettingsPage />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </QueryClientProvider>
        </ThemeProvider>
      </I18nProvider>,
    );

    const usedCard = await screen.findByTestId(`extension-card-${usedId}`);
    expect(usedCard).toHaveTextContent("Bitwarden");
    expect(usedCard).toHaveTextContent("nngceckbapebfimnlniiiahkandclblb");
    expect(screen.getByTestId(`extension-delete-btn-${usedId}`)).toBeDisabled();
    expect(screen.getByTestId(`extension-delete-btn-${freeId}`)).not.toBeDisabled();

    fireEvent.click(screen.getByTestId(`extension-used-by-btn-${usedId}`));
    const usedByList = await screen.findByTestId(`extension-used-by-${usedId}`);
    expect(usedByList).toHaveTextContent("Vault Profile");
    expect(usedByList.textContent).not.toContain("#4");

    fireEvent.click(screen.getByTestId(`extension-delete-btn-${freeId}`));
    await waitFor(() => expect(removeFn).toHaveBeenCalledWith(freeId));

    const badZip = new File([new Uint8Array([9, 9])], "bad.zip");
    fireEvent.change(screen.getByTestId("extensions-file-input"), {
      target: { files: [badZip] },
    });
    expect(await screen.findByTestId("extensions-action-error")).toHaveTextContent(
      "indeterminate_extension_identity",
    );
  });
});
