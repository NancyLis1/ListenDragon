import type { ReactNode, SVGProps } from "react";

export type IconName = "upload" | "search" | "file" | "bookmark" | "settings" | "clock" | "play" | "send" | "close" | "check" | "note" | "list" | "expand" | "captions" | "sparkles" | "info";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
}

const iconPaths: Record<IconName, ReactNode> = {
  upload: <><path d="M12 15V3" /><path d="m7 8 5-5 5 5" /><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" /></>,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
  file: <><path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5M8.5 13h7M8.5 17h5" /></>,
  bookmark: <path d="M6 3h12v18l-6-4-6 4V3Z" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.8 1.8 0 0 0 .36 1.98l.06.06-2.62 2.62-.06-.06a1.8 1.8 0 0 0-1.98-.36 1.8 1.8 0 0 0-1.1 1.65V21h-3.7v-.1A1.8 1.8 0 0 0 9.3 19.25a1.8 1.8 0 0 0-1.98.36l-.06.06-2.62-2.62.06-.06A1.8 1.8 0 0 0 5.06 15a1.8 1.8 0 0 0-1.66-1.1H3.3v-3.7h.1A1.8 1.8 0 0 0 5.05 9.1a1.8 1.8 0 0 0-.36-1.98l-.06-.06 2.62-2.62.06.06a1.8 1.8 0 0 0 1.98.36 1.8 1.8 0 0 0 1.1-1.65V3.1h3.7v.1a1.8 1.8 0 0 0 1.1 1.65 1.8 1.8 0 0 0 1.98-.36l.06-.06 2.62 2.62-.06.06a1.8 1.8 0 0 0-.36 1.98 1.8 1.8 0 0 0 1.65 1.1h.1v3.7h-.1A1.8 1.8 0 0 0 19.4 15Z" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.2 2" /></>,
  play: <path d="m9 6 8 6-8 6V6Z" fill="currentColor" stroke="none" />,
  send: <><path d="m21 3-8.5 18-2.6-7.9L3 10.5 21 3Z" /><path d="m9.9 13.1 4.7-4.7" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  check: <path d="m5 12 4.3 4.3L19.5 6" />,
  note: <><path d="M5 3h14v18H5z" /><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4" /></>,
  list: <><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r=".8" fill="currentColor" stroke="none" /><circle cx="4.5" cy="12" r=".8" fill="currentColor" stroke="none" /><circle cx="4.5" cy="18" r=".8" fill="currentColor" stroke="none" /></>,
  expand: <><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5" /></>,
  captions: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 10h3M14 10h3M7 14h3M14 14h3" /></>,
  sparkles: <><path d="m12 3 1.1 4.1L17 8.2l-3.9 1.1L12 13l-1.1-3.7L7 8.2l3.9-1.1L12 3ZM19 14l.55 2.45L22 17l-2.45.55L19 20l-.55-2.45L16 17l2.45-.55L19 14Z" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
};

export function Icon({ name, ...props }: IconProps) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{iconPaths[name]}</svg>;
}
