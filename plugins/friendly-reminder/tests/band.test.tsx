import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const LINES = [
  '💧 12 mL de água nesta resposta (5% de um copo) · hoje 1,4 L · mês 18 L',
  '⚡ 3,4 Wh · 326 mil tokens · US$ 0,20',
]

// What the engine answers beneath the plugin: nothing of its own to draw, no settings Stop hook.
const engine = (on: On) => {
  on('ui.render', ($, e) => {
    const { Box } = $.ui.resolve(e)
    return <Box key="engine" />
  })
  on('classic.Stop', () => ({}) as never)
}

const props = (isWorking = false) =>
  ({ hasSurvey: false, isWorking, maxRows: 10, bodyColumns: 120 }) as never

test('the reminder shows above the prompt after a response, without a prefix', async ($, on) => {
  engine(on)
  on('process.run', () => ({
    value: {
      exitCode: 0,
      stdout: JSON.stringify({ systemMessage: LINES.join('\n'), language: 'pt' }),
      stderr: '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))

  for (const surface of ['terminal', 'desktop'] as const) {
    const before = await $.ui.mount({ plugin: 'friendly-reminder', surface, component: 'AbovePrompt', props: props() })
    expect(await before.find({ type: 'Text', text: /água/ })).toBeUndefined()
    await before.unmount()
  }

  await $.classic.Stop({ stop_hook_active: false, last_assistant_message: 'oi' } as never)

  for (const surface of ['terminal', 'desktop'] as const) {
    const busy = await $.ui.mount({ plugin: 'friendly-reminder', surface, component: 'AbovePrompt', props: props(true) })
    expect(await busy.find({ type: 'Text', text: /água/ })).toBeUndefined()
    await busy.unmount()

    const ui = await $.ui.mount({ plugin: 'friendly-reminder', surface, component: 'AbovePrompt', props: props() })
    expect((await ui.find({ type: 'Text', text: /água/ }))?.text).toBe(LINES[0])
    expect((await ui.find({ type: 'Text', text: /tokens/ }))?.text).toBe(LINES[1])
    await ui.unmount()
  }

  const ui = await $.ui.mount({ plugin: 'friendly-reminder', surface: 'terminal', component: 'AbovePrompt', props: props() })
  await ui.press({ key: 'hide' })
  expect(await ui.find({ type: 'Text', text: /água/ })).toBeUndefined()
  await ui.unmount()
})

test('a failing script leaves the band empty', async ($, on) => {
  engine(on)
  on('process.run', () => ({
    value: { exitCode: 1, stdout: 'not json', stderr: 'boom', isStdoutTruncated: false, isStderrTruncated: false },
  }))
  await $.classic.Stop({ stop_hook_active: false, last_assistant_message: 'oi' } as never)
  const ui = await $.ui.mount({ plugin: 'friendly-reminder', surface: 'terminal', component: 'AbovePrompt', props: props() })
  expect(await ui.find({ type: 'Text', text: /água/ })).toBeUndefined()
  await ui.unmount()
})

test('settings from /config reach the Python side', { options: { format: 'table', language: 'en' } }, async ($, on) => {
  engine(on)
  const seen: Record<string, string>[] = []
  on('process.run', (_$, e) => {
    seen.push({ ...(e.init?.env ?? {}) })
    return {
      value: {
        exitCode: 0,
        stdout: JSON.stringify({ systemMessage: 'water line', language: 'en' }),
        stderr: '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  await $.classic.Stop({ stop_hook_active: false, last_assistant_message: 'hi' } as never)
  expect(seen[0]?.CLAUDE_PLUGIN_OPTION_FORMAT).toBe('table')
  expect(seen[0]?.CLAUDE_PLUGIN_OPTION_LANGUAGE).toBe('en')
  const ui = await $.ui.mount({ plugin: 'friendly-reminder', surface: 'terminal', component: 'AbovePrompt', props: props() })
  expect((await ui.find({ key: 'hide' }))?.props.label).toBe('Hide')
  await ui.unmount()
})
