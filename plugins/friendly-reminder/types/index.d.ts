export type Reminder = { lines: string[]; language: string }

declare module 'claude-code' {
  interface PluginState {
    'friendly-reminder': {
      last: Reminder | null
      /** The last Stop payload, to measure that response again after a setting changes. */
      lastStop: Record<string, unknown> | null
      isHidden: boolean
      isEditing: boolean
    }
  }
}
