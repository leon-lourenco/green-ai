// Friendly Reminder as a band above the prompt.
//
// After each response the Python package (scripts/friendly-reminder) reads the
// transcript, records the turn and returns the message; this module keeps it
// and draws it above the prompt. A Stop hook's own systemMessage would be
// shown with a "Stop says:" prefix on every line, which a band avoids.
//
// Options opens pickers for the plugin's choice settings. A pick is written to
// the /config row (which reloads this module with the new options) and the
// last response is measured again, so the band shows the change at once.
// Recording the same turn twice is harmless: the history keys rows by turn.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Reminder } from '../types'

const last = atom({ plugin: 'friendly-reminder', key: 'last' } as const, null)
const lastStop = atom({ plugin: 'friendly-reminder', key: 'lastStop' } as const, null)
const isHidden = atom({ plugin: 'friendly-reminder', key: 'isHidden' } as const, false)
const isEditing = atom({ plugin: 'friendly-reminder', key: 'isEditing' } as const, false)

type Words = Record<string, string>

const HIDE: Words = { en: 'Hide', pt: 'Ocultar' }
const OPTIONS: Words = { en: 'Options', pt: 'Opções' }
const DONE: Words = { en: 'Done', pt: 'Concluir' }
const MORE: Words = {
  en: 'Currency and exchange rate: /config',
  pt: 'Moeda e câmbio: /config',
}

// The userConfig fields with fixed choices, in the order they are drawn.
const CHOICES: { field: string; label: Words; options: { value: string; label: Words }[] }[] = [
  {
    field: 'format',
    label: { en: 'Format', pt: 'Formato' },
    options: [
      { value: 'short', label: { en: 'short', pt: 'curto' } },
      { value: 'table', label: { en: 'table', pt: 'tabela' } },
      { value: 'detailed', label: { en: 'detailed', pt: 'detalhado' } },
      { value: 'off', label: { en: 'off (history only)', pt: 'desligado (só histórico)' } },
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
  {
    field: 'comparison',
    label: { en: 'Compare with', pt: 'Comparar com' },
    options: [
      { value: 'progressive', label: { en: 'progressive', pt: 'progressivo' } },
      { value: 'random', label: { en: 'random', pt: 'aleatório' } },
    ],
  },
  {
    field: 'footprint_profile',
    label: { en: 'Estimate', pt: 'Estimativa' },
    options: [
      { value: 'central', label: { en: 'central', pt: 'central' } },
      { value: 'low', label: { en: 'low end', pt: 'mínima' } },
      { value: 'high', label: { en: 'high end', pt: 'máxima' } },
    ],
  },
  {
    field: 'water_scope',
    label: { en: 'Water', pt: 'Água' },
    options: [
      { value: 'full', label: { en: 'cooling + power generation', pt: 'resfriamento + geração de energia' } },
      { value: 'onsite', label: { en: 'cooling only', pt: 'só resfriamento' } },
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

async function measure($: EngineInterface, stop: unknown, env: Record<string, string>): Promise<Reminder | null> {
  const { stdout } = await $.process.run(['python3', `${$.plugin.root}/scripts/friendly-reminder`], {
    stdin: JSON.stringify(stop),
    env,
    timeoutMs: 15000,
  })
  const out = stdout.trim() ? (JSON.parse(stdout) as { systemMessage?: string; language?: string }) : {}
  return out.systemMessage ? { lines: out.systemMessage.split('\n'), language: out.language ?? 'en' } : null
}

async function choose($: EngineInterface, current: Record<string, unknown>, field: string, value: string) {
  const rows = await $.config.list()
  const row =
    rows.find(r => r.key === `friendly-reminder.${field}`) ??
    rows.find(r => r.key.startsWith('friendly-reminder') && r.key.endsWith(`.${field}`))
  if (!row) return
  const { deny } = await $.config.set({ key: row.key, value })
  if (deny) {
    $.ui.toast(deny)
    return
  }
  const stop = await read($, lastStop)
  if (stop === null) return
  try {
    const reminder = await measure($, stop, toEnv({ ...current, [field]: value }))
    await update($, last, () => reminder)
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
      const reminder = await measure($, e, toEnv(current))
      await update($, last, () => reminder)
    } catch {
      // a reminder must never get in the way of the session
    }
    return result
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.props.isWorking || (await read($, isHidden))) {
      return next(e)
    }
    const reminder = await read($, last)
    const editing = await read($, isEditing)
    // With format "off" there is no reminder, but an open panel stays so the pick can be undone.
    if (reminder === null && !editing) {
      return next(e)
    }

    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    // The mobile app draws no Select yet, so it gets no Options button.
    const Select = 'Select' in elements ? elements.Select : undefined
    const language = reminder?.language ?? (current.language === 'pt' ? 'pt' : 'en')
    const [water, ...rest] = reminder?.lines ?? []

    return (
      <Box flexDirection="column">
        {water !== undefined && <Text key="water">{water}</Text>}
        {rest.map((line, i) => (
          <Text key={`line-${i}`} dimColor>
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
            <Text key="more" dimColor>
              {say(MORE, language)}
            </Text>
          </Box>
        )}
        <Box key="actions" flexDirection="row" gap={1}>
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
