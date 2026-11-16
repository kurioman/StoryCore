// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useSettings } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as ReactDOMClient from "react-dom/client";
import { msg } from "@/i18n";
import { AvatarsPage } from "@/features/avatars/AvatarsPage";
import { CommandsPage } from "@/features/commands/CommandsPage";
import { HelpDialog } from "@/features/help/HelpDialog";
import { LibraryPage } from "@/features/library/LibraryPage";
import { MusicPage } from "@/features/music/MusicPage";
import { WelcomePage } from "@/features/welcome/WelcomePage";
import { SetupPage } from "@/features/setup/SetupPage";
import { IconButton, UiProvider } from "@/components/ui";
import { LorePage } from "@/features/lore/LorePage";
import { NewStoryWizard } from "@/features/wizard/NewStoryWizard";
import { PortraitsPage } from "@/features/portraits/PortraitsPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { Sidebar } from "@/features/sidebar/Sidebar";
import { StoryPage } from "@/features/story/StoryPage";
import { cn } from "@/lib/util";
import { matchRoute, useHashPath } from "@/lib/router";
import { useLocalState, useMediaQuery } from "@/lib/hooks";

function App() {
  let hashPath = useHashPath(),
    settings = useSettings(),
    mediaQuery = useMediaQuery(`(min-width: 1024px)`),
    [r, i] = useLocalState(`sidebar-collapsed`, false),
    [a, o] = React.useState(false),
    [s, c] = React.useState(false);
  (React.useEffect(() => {
    let e = settings.data?.theme ?? `dark`;
    document.documentElement.dataset.theme = e;
  }, [settings.data?.theme]),
    React.useEffect(() => {
      document.documentElement.dataset.storyFont = settings.data?.story_font ?? `sans`;
    }, [settings.data?.story_font]),
    React.useEffect(() => {
      document.documentElement.dataset.readingSize = settings.data?.reading_size ?? `comfortable`;
    }, [settings.data?.reading_size]),
    React.useEffect(() => o(false), [hashPath]));
  let l, u;
  l = (u = matchRoute(hashPath, `/story/:id`)) ? (
    <StoryPage storyId={u.id} key={u.id} />
  ) : matchRoute(hashPath, `/new`) ? (
    <NewStoryWizard />
  ) : (u = matchRoute(hashPath, `/avatars/:id`)) ? (
    <AvatarsPage selectedId={u.id} />
  ) : matchRoute(hashPath, `/avatars`) ? (
    <AvatarsPage />
  ) : matchRoute(hashPath, `/lore`) ? (
    <LorePage />
  ) : matchRoute(hashPath, `/portraits`) ? (
    <PortraitsPage />
  ) : matchRoute(hashPath, `/commands`) ? (
    <CommandsPage />
  ) : (u = matchRoute(hashPath, `/settings/:tab`)) ? (
    <SettingsPage tab={u.tab} />
  ) : matchRoute(hashPath, `/settings`) ? (
    <SettingsPage tab="providers" />
  ) : matchRoute(hashPath, `/music`) ? (
    <MusicPage />
  ) : matchRoute(hashPath, `/library`) ? (
    <LibraryPage />
  ) : null;

  let d = matchRoute(hashPath, `/story/:id`)?.id,
    f = (
      <Sidebar
        activeStoryId={d}
        path={hashPath}
        collapsed={mediaQuery ? r : false}
        onToggle={() => (mediaQuery ? i(!r) : o(false))}
        onHelp={() => c(true)}
      />
    );

  // v1.8: the welcome page is full screen, without the sidebar (every unknown address lands there too)
  if (!l)
    return (
      <div className="h-full">
        <ErrorBoundary area={msg("This page")} resetKey={hashPath}>
          {matchRoute(hashPath, `/setup`) ? <SetupPage /> : <WelcomePage />}
        </ErrorBoundary>
        <HelpDialog open={s} onClose={() => c(false)} />
      </div>
    );

  return (
    <div className="flex h-full overflow-hidden">
      {mediaQuery ? (
        f
      ) : (
        <>
          <div
            className={cn(
              `fixed inset-0 z-30 bg-black/50 transition-opacity`,
              a ? `opacity-100` : `pointer-events-none opacity-0`,
            )}
            onClick={() => o(false)}
          />

          <div
            className={cn(
              `fixed inset-y-0 left-0 z-40 transition-transform`,
              a ? `translate-x-0` : `-translate-x-full`,
            )}
          >
            {f}
          </div>
        </>
      )}
      <main className="relative flex min-w-0 flex-1 flex-col">
        {!mediaQuery && (
          <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line px-2">
            <IconButton label={msg("Open library")} onClick={() => o(true)}>
              <Icon.Menu className="size-4" />
            </IconButton>
            <span className="sc-brand text-sm text-accent">{msg("StoryCore")}</span>
            <IconButton label={msg("Help and tour")} className="ml-auto" onClick={() => c(true)}>
              <Icon.CircleQuestionMark className="size-4" />
            </IconButton>
          </div>
        )}
        <div className="min-h-0 flex-1">
          <ErrorBoundary area={msg("This page")} resetKey={hashPath.split(`?`)[0]}>
            {l}
          </ErrorBoundary>
        </div>
      </main>
      <HelpDialog open={s} onClose={() => c(false)} />
    </div>
  );
}

var appQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5e3,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

(0, ReactDOMClient.createRoot)(document.getElementById(`root`)).render(
  <React.StrictMode>
    <QueryClientProvider client={appQueryClient}>
      <UiProvider>
        <App />
      </UiProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
