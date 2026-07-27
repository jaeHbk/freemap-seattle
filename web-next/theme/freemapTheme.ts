import { defineTheme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";

export const freemapTheme = defineTheme({
  name: "freemap",
  extends: neutralTheme,
  tokens: {
    "--color-background-body": ["#F7F8F5", "#171C19"],
    "--color-background-surface": ["#FFFFFF", "#202723"],
    "--color-background-card": ["#FFFFFF", "#1B211E"],
    "--color-background-popover": ["#FFFFFF", "#1B211E"],
    "--color-background-muted": ["#EEF1ED", "#202723"],
    "--color-accent": ["#0D7A50", "#51C28B"],
    "--color-accent-muted": ["#E3F2EB", "#1C3D30"],
    "--color-text-primary": ["#19221E", "#F4F7F5"],
    "--color-text-secondary": ["#5F6B65", "#AAB5AF"],
    "--color-text-accent": ["#0B6D47", "#7AD8A7"],
    "--color-icon-primary": ["#19221E", "#F4F7F5"],
    "--color-icon-secondary": ["#68756E", "#AAB5AF"],
    "--color-icon-accent": ["#0D7A50", "#7AD8A7"],
    "--color-on-accent": ["#FFFFFF", "#10251B"],
    "--color-border": ["#DDE3DF", "#FFFFFF1F"],
    "--color-border-emphasized": ["#B9C5BE", "#65726B"],
    "--font-family-body":
      "var(--font-sans), -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif",
    "--font-family-heading":
      "var(--font-sans), -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif",
    "--radius-container": "8px",
    "--radius-page": "8px",
  },
  components: {
    appshell: {
      base: {
        backgroundColor: "var(--color-background-body)",
      },
    },
    topnav: {
      base: {
        minHeight: "56px",
      },
    },
    button: {
      base: {
        borderRadius: "6px",
      },
    },
  },
});
