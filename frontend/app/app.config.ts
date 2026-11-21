const outlineField = 'bg-elevated/40 hover:bg-elevated/55 disabled:bg-elevated/20';
const cardSurface =
  'border border-(--fbc-border-soft) bg-elevated/20 divide-y divide-default ring-0';
const overlaySurface = 'fbc-overlay-surface bg-transparent';
const floatingSurface =
  'fbc-floating-surface rounded-lg bg-(--fbc-floating-bg) shadow-(--fbc-floating-shadow) ring-0';

export default defineAppConfig({
  ui: {
    colors: {
      primary: 'indigo',
      secondary: 'amber',
      success: 'emerald',
      neutral: 'stone',
    },
    button: {
      compoundVariants: [
        {
          color: 'neutral',
          variant: 'outline',
          class:
            'bg-transparent hover:bg-elevated/30 active:bg-elevated/40 disabled:bg-transparent aria-disabled:bg-transparent',
        },
        {
          color: 'neutral',
          variant: 'soft',
          class: 'bg-elevated/30 hover:bg-elevated/45 active:bg-elevated/55',
        },
        {
          color: 'neutral',
          variant: 'ghost',
          class: 'hover:bg-elevated/30 active:bg-elevated/40 focus-visible:bg-elevated/30',
        },
      ],
      defaultVariants: { size: 'sm' },
    },
    card: {
      slots: { root: 'min-w-0 max-w-full rounded-lg overflow-hidden' },
      variants: {
        variant: {
          outline: { root: cardSurface },
          soft: { root: 'bg-elevated/20 divide-y divide-default' },
          subtle: { root: cardSurface },
        },
      },
    },
    empty: {
      variants: {
        variant: { outline: { root: 'border border-dashed border-default bg-muted/10 ring-0' } },
      },
      defaultVariants: { variant: 'outline' },
    },
    formField: {
      slots: {
        label: 'block font-semibold text-default',
        description: 'text-sm text-toned',
        help: 'text-sm text-toned',
        error: 'text-sm text-error',
      },
    },
    input: { variants: { variant: { outline: outlineField } } },
    textarea: { variants: { variant: { outline: outlineField } } },
    selectMenu: {
      slots: { content: floatingSurface },
      variants: { variant: { outline: outlineField } },
    },
    dropdownMenu: { slots: { content: floatingSurface } },
    popover: { slots: { content: floatingSurface } },
    modal: { slots: { content: overlaySurface, footer: 'justify-end' } },
    toast: { slots: { root: overlaySurface } },
  },
});
