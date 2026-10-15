// Friendly Reminder as a band above the prompt.
//
// After each response the Python package (scripts/friendly-reminder) reads the
// transcript, records the turn and returns the message; this module keeps it
// and draws it above the prompt. A Stop hook's own systemMessage would be
// shown with a "Stop says:" prefix on every line, which a band avoids.

import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Reminder } from '../types'

const last = atom({ plugin: 'friendly-reminder', key: 'last' } as const, null)
const isHidden = atom({ plugin: 'friendly-reminder', key: 'isHidden' } as const, false)

const HIDE = { en: 'Hide', pt: 'Ocultar' } as Record<string, string>

export const register: Register = (on, options) => {
  // The Python side reads its settings the way a command hook would.
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(options)) {
    if (value !== undefined && value !== null) {
      env[`CLAUDE_PLUGIN_OPTION_${key.toUpperCase()}`] = String(value)
    }
  }

  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    try {
      const { stdout } = await $.process.run(['python3', `${$.plugin.root}/scripts/friendly-reminder`], {
        stdin: JSON.stringify(e),
        env,
        timeoutMs: 15000,
      })
      const out = stdout.trim() ? (JSON.parse(stdout) as { systemMessage?: string; language?: string }) : {}
      const reminder: Reminder | null = out.systemMessage
        ? { lines: out.systemMessage.split('\n'), language: out.language ?? 'en' }
        : null
      await update($, last, () => reminder)
    } catch {
      // a reminder must never get in the way of the session
    }
    return result
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const reminder = await read($, last)
    if (e.props.hasSurvey || e.props.isWorking || reminder === null || (await read($, isHidden))) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    const [water, ...rest] = reminder.lines

    return (
      <Box flexDirection="column">
        <Text key="water">{water}</Text>
        {rest.map((line, i) => (
          <Text key={`line-${i}`} dimColor>
            {line}
          </Text>
        ))}
        <Button
          key="hide"
          label={HIDE[reminder.language] ?? HIDE.en!}
          onPress={() => update($, isHidden, () => true)}
        />
      </Box>
    )
  })
}
