/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"], // Enable class-based dark mode for next-themes
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // === SAPTIVA SEMANTIC COLORS (HSL from CSS variables) ===
        background: "hsl(var(--background))",
        surface: "hsl(var(--surface))",
        'surface-2': "hsl(var(--surface-2))",
        foreground: "hsl(var(--foreground))",
        muted: "hsl(var(--muted))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-fg))",
          600: "hsl(var(--primary-600))",
          700: "hsl(var(--primary-700))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        danger: "hsl(var(--danger))",

        // Legacy aliases for backwards compatibility
        bg: "hsl(var(--background))",
        text: "hsl(var(--foreground))",
        'text-muted': "hsl(var(--muted))",
        link: "hsl(var(--primary))",
        sidebar: "hsl(var(--surface))",

        // Legacy SAPTIVA colors para compatibilidad
        saptiva: {
          mint: '#2DD4BF',
          blue: '#4472C4',
          lightBlue: '#5B9BD5',
          orange: '#ED7D31',
          yellow: '#FFC000',
          green: '#2DD4BF',
          purple: '#954F72',
          dark: '#0B1120',
          charcoal: '#1e293b',
          slate: '#44546A',
          silver: '#94a3b8',
          light: '#F9FAFB',
          hyperlink: '#2DD4BF',
        },

        // Grays mantenidos para elementos neutros
        gray: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
        },
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'ui-sans-serif', 'system-ui'], // SAPTIVA Lab token system
        mono: ['Fira Code', 'monospace'],
      },
      maxWidth: {
        'container': '1200px', // SAPTIVA container token
      },
      fontSize: {
        // Escala tipográfica específica del plan: sm:13, base:15, lg:18, xl:24
        sm: ['13px', { lineHeight: '18px' }],
        base: ['15px', { lineHeight: '22px' }],
        lg: ['18px', { lineHeight: '26px' }],
        xl: ['24px', { lineHeight: '32px' }],
        // Mantenemos tamaños adicionales para flexibilidad
        xs: ['12px', { lineHeight: '16px' }],
        '2xl': ['32px', { lineHeight: '40px' }],
        '3xl': ['40px', { lineHeight: '48px' }],
      },
      fontWeight: {
        // Weights específicos del Lab: 400/700 solamente
        normal: '400',
        bold: '700',
      },
      borderRadius: {
        // SAPTIVA token system using CSS variable
        'sm': 'calc(var(--radius) - 4px)',
        'md': 'var(--radius)',
        'lg': 'calc(var(--radius) + 4px)',
        'xl': 'var(--radius)',
        'none': '0',
        'DEFAULT': '0.25rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
        'full': '9999px',
      },
      boxShadow: {
        // Shadow específica del plan
        'card': '0 6px 20px rgba(0,0,0,0.24)',
        // Mantener shadows estándar
        'sm': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'DEFAULT': '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
        'md': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        'lg': '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
        'none': 'none',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'typing': 'typing 1.5s steps(30, end) infinite',
        'fade-in': 'fadeIn 0.6s ease-in-out',
        // P0-UX-HIST-001: Highlight animation for new conversations
        'highlight-fade': 'highlightFade 2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        typing: {
          '0%, 50%': { opacity: '1' },
          '51%, 100%': { opacity: '0' },
        },
        // P0-UX-HIST-001: Highlight fade keyframes
        highlightFade: {
          '0%': { backgroundColor: 'rgba(73, 247, 217, 0.15)', borderColor: 'rgba(73, 247, 217, 0.6)' },
          '100%': { backgroundColor: 'rgba(73, 247, 217, 0)', borderColor: 'transparent' },
        },
      },
      // Typography plugin configuration for dual theme support
      // FIX: P3 ui-font-layout-break - ensure consistent font and layout
      typography: {
        DEFAULT: {
          css: {
            // FIX: Inherit font-family from parent to prevent font switching
            fontFamily: 'inherit',
            // FIX: Ensure text wraps properly
            overflowWrap: 'break-word',
            wordBreak: 'break-word',
            // Color tokens
            '--tw-prose-body': 'hsl(var(--foreground))',
            '--tw-prose-headings': 'hsl(var(--foreground))',
            '--tw-prose-links': 'hsl(var(--primary))',
            '--tw-prose-bold': 'hsl(var(--foreground))',
            '--tw-prose-counters': 'hsl(var(--muted))',
            '--tw-prose-bullets': 'hsl(var(--primary))',
            '--tw-prose-hr': 'hsl(var(--border))',
            '--tw-prose-quotes': 'hsl(var(--foreground))',
            '--tw-prose-quote-borders': 'hsl(var(--primary))',
            '--tw-prose-captions': 'hsl(var(--muted))',
            '--tw-prose-code': 'hsl(var(--primary))',
            '--tw-prose-pre-code': 'hsl(var(--foreground))',
            '--tw-prose-pre-bg': 'hsl(var(--surface))',
            '--tw-prose-th-borders': 'hsl(var(--border))',
            '--tw-prose-td-borders': 'hsl(var(--border))',
            // FIX: Ensure headings inherit font
            'h1, h2, h3, h4, h5, h6': {
              fontFamily: 'inherit',
            },
            // FIX: Ensure paragraphs inherit font
            'p': {
              fontFamily: 'inherit',
            },
            // FIX: Ensure lists inherit font
            'ul, ol, li': {
              fontFamily: 'inherit',
            },
            // FIX: Code blocks use monospace but stay in container
            'pre': {
              fontFamily: 'var(--font-mono, ui-monospace, monospace)',
              overflowX: 'auto',
              maxWidth: '100%',
            },
            'code': {
              fontFamily: 'var(--font-mono, ui-monospace, monospace)',
            },
            // Invert colors for dark mode
            '--tw-prose-invert-body': 'hsl(var(--foreground))',
            '--tw-prose-invert-headings': 'hsl(var(--foreground))',
            '--tw-prose-invert-links': 'hsl(var(--primary))',
            '--tw-prose-invert-bold': 'hsl(var(--foreground))',
            '--tw-prose-invert-counters': 'hsl(var(--muted))',
            '--tw-prose-invert-bullets': 'hsl(var(--primary))',
            '--tw-prose-invert-hr': 'hsl(var(--border))',
            '--tw-prose-invert-quotes': 'hsl(var(--foreground))',
            '--tw-prose-invert-quote-borders': 'hsl(var(--primary))',
            '--tw-prose-invert-captions': 'hsl(var(--muted))',
            '--tw-prose-invert-code': 'hsl(var(--primary))',
            '--tw-prose-invert-pre-code': 'hsl(var(--foreground))',
            '--tw-prose-invert-pre-bg': 'hsl(var(--surface))',
            '--tw-prose-invert-th-borders': 'hsl(var(--border))',
            '--tw-prose-invert-td-borders': 'hsl(var(--border))',
          },
        },
      },
    },
  },
  plugins: [
    (() => {
      try {
        return require('@tailwindcss/forms')
      } catch (error) {
        console.warn('[@tailwindcss/forms] plugin not found, continuing without it.')
        return null
      }
    })(),
    (() => {
      try {
        return require('@tailwindcss/typography')
      } catch (error) {
        console.warn('[@tailwindcss/typography] plugin not found, continuing without it.')
        return null
      }
    })(),
  ].filter(Boolean),
}
