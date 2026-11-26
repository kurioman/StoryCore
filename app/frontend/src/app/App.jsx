// Reconstructed from the StoryCore v1.7.0 compiled bundle (see DEVONLY/13_FRONTEND_SOURCE.md).
import { useSettings } from "@/api/queries";
import * as React from "react";
import * as Icon from "lucide-react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as ReactDOMClient from "react-dom/client";
import { msg } from "@/i18n";
import { HelpDialog } from "@/features/help/HelpDialog";
import { WelcomePage } from "@/features/welcome/WelcomePage";
import { IconButton, UiProvider } from "@/components/ui";
import { Logo, Sidebar } from "@/features/sidebar/Sidebar";
import { cn } from "@/lib/util";
import { matchRoute, navigate, useHashPath } from "@/lib/router";
import { useLocalState, useMediaQuery } from "@/lib/hooks";
import { usePhoneLayout, useShellRequests } from "@/lib/layout";
import { Spinner } from "@/components/ui";

// v0.5: every page is its own file, downloaded the first time it is opened (the welcome page and the sidebar are in the
// main file). Faster first display, above all on a phone. The play screen and the library are fetched in the
// background shortly after start, so opening them stays instant.
const AvatarsPage = React.lazy(() => import("@/features/avatars/AvatarsPage").then((m) => ({ default: m.AvatarsPage })));
const CreatorPage = React.lazy(() => import("@/features/creator/CreatorPage").then((m) => ({ default: m.CreatorPage })));
const CommandsPage = React.lazy(() => import("@/features/commands/CommandsPage").then((m) => ({ default: m.CommandsPage })));
const LibraryPage = React.lazy(() => import("@/features/library/LibraryPage").then((m) => ({ default: m.LibraryPage })));
const MusicPage = React.lazy(() => import("@/features/music/MusicPage").then((m) => ({ default: m.MusicPage })));
const SetupPage = React.lazy(() => import("@/features/setup/SetupPage").then((m) => ({ default: m.SetupPage })));
const LorePage = React.lazy(() => import("@/features/lore/LorePage").then((m) => ({ default: m.LorePage })));
const NewStoryWizard = React.lazy(() => import("@/features/wizard/NewStoryWizard").then((m) => ({ default: m.NewStoryWizard })));
const PortraitsPage = React.lazy(() => import("@/features/portraits/PortraitsPage").then((m) => ({ default: m.PortraitsPage })));
const SettingsPage = React.lazy(() => import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const StoryPage = React.lazy(() => import("@/features/story/StoryPage").then((m) => ({ default: m.StoryPage })));

function preloadCommonPages() {
  import("@/features/library/LibraryPage");
  import("@/features/story/StoryPage");
}

function PageLoading() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner />
    </div>
  );
}

function App() {
  React.useEffect(() => {
    let t = window.setTimeout(preloadCommonPages, 1500);
    return () => window.clearTimeout(t);
  }, []);
  let hashPath = useHashPath(),
    settings = useSettings(),
    mediaQuery = useMediaQuery(`(min-width: 1024px)`),
    [r, i] = useLocalState(`sidebar-collapsed`, false),
    [a, o] = React.useState(false),
    [s, c] = React.useState(false),
    phone = usePhoneLayout();
  // the phone play screen has its own single top bar, with the ☰ and "?" buttons (lib/layout.js)
  useShellRequests(
    React.useCallback(() => o(true), []),
    React.useCallback(() => c(true), []),
  );
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
    React.useEffect(() => {
      document.documentElement.dataset.dialogue = settings.data?.dialogue_style ?? `cinematic`;
    }, [settings.data?.dialogue_style]),
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
  ) : (u = matchRoute(hashPath, `/creator/:id`)) ? (
    <CreatorPage worldId={u.id} />
  ) : matchRoute(hashPath, `/creator`) ? (
    <CreatorPage />
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
  ) : matchRoute(hashPath, `/mobile`) ? (
    <SettingsPage tab="phone" />
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

  // v0.5: the welcome page is full screen, without the sidebar (every unknown address lands there too)
  if (!l)
    return (
      <div className="h-full">
        <ErrorBoundary area={msg("This page")} resetKey={hashPath}>
          <React.Suspense fallback={<PageLoading />}>
            {matchRoute(hashPath, `/setup`) ? <SetupPage /> : <WelcomePage />}
          </React.Suspense>
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
        {!mediaQuery && !(phone && d) && (
          // narrow screens and phones: ☰ | StoryCore logo in the middle (back to the title screen) | ?
          <div className="grid h-12 shrink-0 grid-cols-[2.75rem_1fr_2.75rem] items-center border-b border-line px-1">
            <IconButton label={msg("Open library")} onClick={() => o(true)} className="size-10">
              <Icon.Menu className="size-5" />
            </IconButton>
            <button
              type="button"
              onClick={() => navigate(`/`)}
              className="mx-auto flex items-center gap-2 rounded-md px-2 py-1"
              aria-label={msg("Home")}
            >
              <Logo />
              <span className="sc-brand text-[15px] text-accent">{msg("StoryCore")}</span>
            </button>
            <IconButton label={msg("Help and tour")} onClick={() => c(true)} className="size-10">
              <Icon.CircleQuestionMark className="size-5" />
            </IconButton>
          </div>
        )}
        <div className="min-h-0 flex-1">
          <ErrorBoundary area={msg("This page")} resetKey={hashPath.split(`?`)[0]}>
            <React.Suspense fallback={<PageLoading />}>{l}</React.Suspense>
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
