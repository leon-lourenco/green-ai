export type Reminder = { lines: string[]; language: string }

declare module 'claude-code' {
  interface PluginState {
    'friendly-reminder': { last: Reminder | null; isHidden: boolean }
  }
}
