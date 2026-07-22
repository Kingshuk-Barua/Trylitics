import type { Config } from 'tailwindcss';

/** The instrument-panel palette. Nothing outside this list is used. */
export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: '#0B0F14',
        panel: '#141B23',
        line: '#1F2A35',
        dim: '#8FA3B0',
        bright: '#E8EEF2',
        accent: '#3FB6A8',
        ramp: {
          1: '#1B2A38', 2: '#24506B', 3: '#2E7C93',
          4: '#63B39B', 5: '#C8D98A', 6: '#F2C14E',
        },
        nodata: '#FFFFFF',
      },
      fontFamily: {
        display: ['var(--font-display)', 'ui-sans-serif', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      borderRadius: { DEFAULT: '4px', sm: '4px', md: '4px', lg: '4px' },
      maxWidth: { shell: '1440px' },
      transitionDuration: { DEFAULT: '160ms' },
    },
  },
  plugins: [],
} satisfies Config;
