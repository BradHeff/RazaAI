"""Terminal controls preserve the active reply while a model is streaming."""

import asyncio
import threading
import unittest
from textual.widgets import Input
from app.tui.app import RazaTUI


class SlowAgent:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def ask(self, prompt, on_stream=None, **kwargs):
        self.started.set()
        self.release.wait(5)
        if on_stream:
            on_stream('done')
        return 'done'


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_and_debug_preserve_inflight_turn(self):
        agent = SlowAgent()
        app = RazaTUI(agent=agent)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            prompt = app.query_one('#prompt', Input)
            prompt.value = 'hello'
            task = asyncio.create_task(pilot.press('enter'))
            try:
                for _ in range(100):
                    if agent.started.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(app._busy)
                active = app._active_assistant
                await app.action_clear_chat()
                app.action_toggle_debug()
                app._focus_prompt()
                self.assertTrue(prompt.disabled)
                self.assertTrue(active.is_mounted)
            finally:
                agent.release.set()
                await task
            for _ in range(100):
                if not app._busy:
                    break
                await asyncio.sleep(.01)
            await pilot.pause()
            self.assertFalse(app._busy)
            self.assertFalse(prompt.disabled)
            self.assertEqual(active._stream_text, 'done')
            self.assertIs(app.focused, prompt)


if __name__ == '__main__':
    unittest.main()
