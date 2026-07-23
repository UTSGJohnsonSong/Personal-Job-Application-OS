import type { Config } from "tailwindcss";

/**
 * Light silver, frosted glass.
 *
 * The pages were written against a dark palette — `text-white` for primary
 * text, ascending greys for secondary and borders. Rather than rewrite every
 * component, the scale is redefined here so the same class names produce the
 * light theme: `white` becomes ink, and the grey ramp runs from ink down to
 * hairline. The names now describe position in the hierarchy rather than
 * literal colour, which is the trade for not touching a dozen files.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Primary ink. Apple's label colour, not pure black — pure black on a
        // light ground reads as harsh at small sizes.
        white: "#1d1d1f",
        gray: {
          50: "#0a0a0b",
          100: "#1d1d1f",
          200: "#2c2c2e",
          300: "#48484a",   // strong secondary
          400: "#6e6e73",   // secondary label
          500: "#86868b",   // tertiary label
          600: "#a1a1a6",   // quaternary / hints
          700: "#c9c9ce",   // separators
          800: "#dcdce1",   // hairline borders
          900: "#ececed",   // subtle fills and tracks
        },
        bg: "#f5f5f7",
        // Translucent so the frosted blur in globals.css has something to do.
        panel: "rgba(255, 255, 255, 0.72)",
        muted: "#86868b",
        accent: "#0071e3",
        emerald: {
          300: "#0f7a52", 400: "#12805a", 500: "#1a8f66",
          800: "#b7e4cd", 900: "#e3f5ec", 950: "#f0faf5",
        },
        amber: {
          300: "#9a6400", 400: "#a86f00",
          800: "#f0d9a8", 900: "#fdf3e0", 950: "#fefaf2",
        },
        red: {
          300: "#c0392b", 400: "#cc3b2c",
          800: "#f3c4bd", 900: "#fdecea", 950: "#fef6f5",
        },
        blue: {
          300: "#0058b0", 400: "#0071e3",
          800: "#c2ddf7", 900: "#e8f2fd", 950: "#f4f9fe",
        },
      },
      borderRadius: {
        DEFAULT: "0.625rem",
        lg: "1rem",
        xl: "1.25rem",
      },
      boxShadow: {
        glass: "0 1px 2px rgba(0,0,0,0.04), 0 8px 24px -12px rgba(0,0,0,0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
