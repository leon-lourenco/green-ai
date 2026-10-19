export type GardenView = { summary: string[]; full: string[]; language: string }

declare module 'claude-code' {
  interface PluginState {
    'virtual-garden': {
      last: GardenView | null
      /** The last Stop payload, to draw that response again after a setting changes. */
      lastStop: Record<string, unknown> | null
      /** The view picked with "View garden"; null follows the format setting. */
      view: 'summary' | 'full' | null
      isHidden: boolean
      isEditing: boolean
    }
  }
}
