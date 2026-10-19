// Virtual Garden as a band above the prompt.
//
// After each response the Python package (scripts/virtual-garden) reads the
// transcript, grows the garden with the turn and returns two views of it: a
// one-line summary and the full garden. This module keeps both and draws the
// one the format asks for; "View garden" flips between them without running
// Python again.
//
// Options opens pickers for the plugin's settings. A pick is written to the
// /config row (which reloads this module with the new options) and the last
// response is drawn again. Python applies a turn only once, so drawing the
// same turn again never grows the plant twice.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { GardenView } from '../types'

const last = atom({ plugin: 'virtual-garden', key: 'last' } as const, null)
const lastStop = atom({ plugin: 'virtual-garden', key: 'lastStop' } as const, null)
const view = atom({ plugin: 'virtual-garden', key: 'view' } as const, null)
const isHidden = atom({ plugin: 'virtual-garden', key: 'isHidden' } as const, false)
const isEditing = atom({ plugin: 'virtual-garden', key: 'isEditing' } as const, false)

type Words = Record<string, string>

const HIDE: Words = { en: 'Hide', pt: 'Ocultar' }
const OPTIONS: Words = { en: 'Options', pt: 'Opções' }
const DONE: Words = { en: 'Done', pt: 'Concluir' }
const SHOW_FULL: Words = { en: 'View garden', pt: 'Ver jardim' }
const SHOW_SUMMARY: Words = { en: 'Collapse', pt: 'Recolher' }

// The userConfig fields, in the order they are drawn.
const CHOICES: { field: string; label: Words; options: { value: string; label: Words }[] }[] = [
  {
    field: 'format',
    label: { en: 'Format', pt: 'Formato' },
    options: [
      { value: 'short', label: { en: 'one line', pt: 'uma linha' } },
      { value: 'full', label: { en: 'full garden', pt: 'jardim completo' } },
      { value: 'off', label: { en: 'off (keeps growing)', pt: 'desligado (continua crescendo)' } },
    ],
  },
  {
    field: 'species',
    label: { en: 'Plant', pt: 'Planta' },
    options: [
      { value: 'current', label: { en: 'keep the current one', pt: 'manter a atual' } },
      { value: 'bonsai', label: { en: '🎍 Bonsai', pt: '🎍 Bonsai' } },
      { value: 'cactus', label: { en: '🌵 Cactus', pt: '🌵 Mandacaru' } },
      { value: 'sakura', label: { en: '🌸 Sakura', pt: '🌸 Cerejeira' } },
      { value: 'ipe', label: { en: '🌼 Golden Ipê', pt: '🌼 Ipê-amarelo' } },
    ],
  },
  {
    field: 'language',
    label: { en: 'Language', pt: 'Idioma' },
    options: [
      { value: 'auto', label: { en: 'automatic', pt: 'automático' } },
      { value: 'en', label: { en: 'English', pt: 'English' } },
      { value: 'pt', label: { en: 'Português', pt: 'Português' } },
    ],
  },
]

const say = (words: Words, language: string) => words[language] ?? words.en!

// The Python side reads its settings the way a command hook would.
const toEnv = (options: Record<string, unknown>) => {
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(options)) {
    if (value !== undefined && value !== null) {
      env[`CLAUDE_PLUGIN_OPTION_${key.toUpperCase()}`] = String(value)
    }
  }
  return env
}

async function tend($: EngineInterface, stop: unknown, env: Record<string, string>): Promise<GardenView | null> {
  const { stdout } = await $.process.run(['python3', `${$.plugin.root}/scripts/virtual-garden`], {
    stdin: JSON.stringify(stop),
    env,
    timeoutMs: 15000,
  })
  if (!stdout.trim()) return null
  const out = JSON.parse(stdout) as Partial<GardenView>
  return out.summary && out.full ? { summary: out.summary, full: out.full, language: out.language ?? 'en' } : null
}

async function choose($: EngineInterface, current: Record<string, unknown>, field: string, value: string) {
  const rows = await $.config.list()
  const row =
    rows.find(r => r.key === `virtual-garden.${field}`) ??
    rows.find(r => r.key.startsWith('virtual-garden') && r.key.endsWith(`.${field}`))
  if (!row) return
  const { deny } = await $.config.set({ key: row.key, value })
  if (deny) {
    $.ui.toast(deny)
    return
  }
  if (field === 'format') await update($, view, () => null)
  const stop = await read($, lastStop)
  if (stop === null) return
  try {
    const garden = await tend($, stop, toEnv({ ...current, [field]: value }))
    await update($, last, () => garden)
  } catch {
    // keep the band as it was
  }
}

export const register: Register = (on, options) => {
  const current = options as Record<string, unknown>

  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    try {
      await update($, lastStop, () => e as unknown as Record<string, unknown>)
      const garden = await tend($, e, toEnv(current))
      await update($, last, () => garden)
    } catch {
      // the garden must never get in the way of the session
    }
    return result
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.props.isWorking || (await read($, isHidden))) {
      return next(e)
    }
    const garden = await read($, last)
    const editing = await read($, isEditing)
    const off = current.format === 'off'
    // With format "off" the garden is not drawn, but an open panel stays so the pick can be undone.
    if ((garden === null || off) && !editing) {
      return next(e)
    }

    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    // The mobile app draws no Select yet, so it gets no Options button.
    const Select = 'Select' in elements ? elements.Select : undefined
    const language = garden?.language ?? (current.language === 'pt' ? 'pt' : 'en')
    const shown = (await read($, view)) ?? (current.format === 'full' ? 'full' : 'summary')
    const lines = garden && !off ? garden[shown] : []

    return (
      <Box flexDirection="column">
        {lines.map((line, i) => (
          <Text key={`line-${i}`} dimColor={shown === 'summary' && i > 0}>
            {line}
          </Text>
        ))}
        {editing && Select && (
          <Box key="options" flexDirection="column" marginTop={1}>
            {CHOICES.map(choice => (
              <Select
                key={`option-${choice.field}`}
                label={`${say(choice.label, language)}: `}
                value={String(current[choice.field] ?? choice.options[0]!.value)}
                options={choice.options.map(o => ({ value: o.value, label: say(o.label, language) }))}
                onSelect={(value: string) => choose($, current, choice.field, value)}
              />
            ))}
          </Box>
        )}
        <Box key="actions" flexDirection="row" gap={1}>
          {garden && !off && (
            <Button
              key="view"
              label={say(shown === 'full' ? SHOW_SUMMARY : SHOW_FULL, language)}
              onPress={() => update($, view, () => (shown === 'full' ? 'summary' : 'full'))}
            />
          )}
          {Select && (
            <Button
              key="options"
              label={say(editing ? DONE : OPTIONS, language)}
              onPress={() => update($, isEditing, open => !open)}
            />
          )}
          <Button
            key="hide"
            label={say(HIDE, language)}
            onPress={async () => {
              await update($, isEditing, () => false)
              await update($, isHidden, () => true)
            }}
          />
        </Box>
      </Box>
    )
  })
}
