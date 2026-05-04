export function useShareShortcutHelp() {
  return useState<boolean>('share-shortcut-help', () => false);
}
