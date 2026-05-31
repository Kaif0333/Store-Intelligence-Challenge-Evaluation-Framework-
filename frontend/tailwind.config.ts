import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
      extend: {
          "colors": {
              "primary-fixed": "#6ffbbe",
              "on-tertiary-container": "#740043",
              "on-secondary-fixed-variant": "#004e5c",
              "on-primary-fixed-variant": "#005236",
              "inverse-on-surface": "#2e3037",
              "background": "#111319",
              "on-error": "#690005",
              "secondary-container": "#03b5d3",
              "on-background": "#e2e2eb",
              "on-surface": "#e2e2eb",
              "outline-variant": "#3c4a42",
              "outline": "#86948a",
              "secondary-fixed-dim": "#4cd7f6",
              "on-primary-container": "#00422b",
              "surface-container-low": "#191b22",
              "on-surface-variant": "#bbcabf",
              "secondary": "#4cd7f6",
              "primary": "#4edea3",
              "surface-bright": "#373940",
              "on-error-container": "#ffdad6",
              "surface-container-highest": "#33343b",
              "inverse-surface": "#e2e2eb",
              "surface-container-high": "#282a30",
              "on-tertiary-fixed": "#3e0022",
              "primary-container": "#10b981",
              "on-primary": "#003824",
              "secondary-fixed": "#acedff",
              "tertiary-fixed-dim": "#ffb0cd",
              "surface-tint": "#4edea3",
              "tertiary-container": "#ff72b1",
              "on-secondary-container": "#00424e",
              "error": "#ffb4ab",
              "on-tertiary": "#640039",
              "surface-dim": "#111319",
              "primary-fixed-dim": "#4edea3",
              "on-secondary-fixed": "#001f26",
              "surface-container": "#1e1f26",
              "on-secondary": "#003640",
              "inverse-primary": "#006c49",
              "error-container": "#93000a",
              "tertiary": "#ffb0cd",
              "tertiary-fixed": "#ffd9e4",
              "on-primary-fixed": "#002113",
              "surface": "#111319",
              "surface-container-lowest": "#0c0e14",
              "on-tertiary-fixed-variant": "#8c0053",
              "surface-variant": "#33343b"
          },
          "borderRadius": {
              "DEFAULT": "0.25rem",
              "lg": "0.5rem",
              "xl": "0.75rem",
              "full": "9999px"
          },
          "spacing": {
              "card-gap": "20px",
              "sidebar-width": "260px",
              "container-padding": "24px",
              "gutter": "16px",
              "unit": "4px"
          },
          "fontFamily": {
              "headline-lg": ["Geist", "sans-serif"],
              "body-lg": ["Geist", "sans-serif"],
              "display-md": ["Geist", "sans-serif"],
              "headline-lg-mobile": ["Geist", "sans-serif"],
              "display-lg": ["Geist", "sans-serif"],
              "mono-data": ["JetBrains Mono", "monospace"],
              "body-sm": ["Geist", "sans-serif"],
              "label-caps": ["Geist", "sans-serif"]
          },
          "fontSize": {
              "headline-lg": ["24px", { "lineHeight": "32px", "fontWeight": "600" }],
              "body-lg": ["16px", { "lineHeight": "24px", "fontWeight": "400" }],
              "display-md": ["36px", { "lineHeight": "44px", "letterSpacing": "-0.02em", "fontWeight": "600" }],
              "headline-lg-mobile": ["20px", { "lineHeight": "28px", "fontWeight": "600" }],
              "display-lg": ["48px", { "lineHeight": "56px", "letterSpacing": "-0.02em", "fontWeight": "700" }],
              "mono-data": ["14px", { "lineHeight": "20px", "fontWeight": "500" }],
              "body-sm": ["14px", { "lineHeight": "20px", "fontWeight": "400" }],
              "label-caps": ["12px", { "lineHeight": "16px", "letterSpacing": "0.05em", "fontWeight": "600" }]
          },
          "keyframes": {
              "fade-in-up": {
                  "0%": { opacity: "0", transform: "translateY(20px)" },
                  "100%": { opacity: "1", transform: "translateY(0)" }
              },
              "shimmer": {
                  "0%": { backgroundPosition: "200% center" },
                  "100%": { backgroundPosition: "-200% center" }
              }
          },
          "animation": {
              "fade-in-up": "fade-in-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards",
              "shimmer": "shimmer 3s linear infinite"
          }
      }
  },
  plugins: []
};

export default config;
