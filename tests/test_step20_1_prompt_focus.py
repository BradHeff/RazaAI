import asyncio

from textual.widgets import Input

from app.tui.app import RazaTUI


class FakeAgent:
    def __init__(self):
        self.prompts=[]
    def ask(self, prompt):
        self.prompts.append(prompt)
        return f"Echo: {prompt}"


async def exercise():
    agent=FakeAgent()
    app=RazaTUI(agent=agent)

    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        prompt=app.query_one("#prompt", Input)

        assert app.focused is prompt
        assert prompt.disabled is False
        assert prompt.region.height >= 3
        assert prompt.region.width > 20
        print("[PASS] prompt is visible, enabled, and focused after first layout")

        await pilot.press("h", "e", "l", "l", "o")
        await pilot.pause()
        assert prompt.value == "hello"
        print("[PASS] keyboard input reaches the anchored prompt")

        await pilot.press("enter")
        for _ in range(30):
            await pilot.pause(0.02)
            if agent.prompts:
                break
        assert agent.prompts == ["hello"]
        print("[PASS] Enter submits typed text to the existing RazaAgent pipeline")

        # Clicking anywhere in the prompt must return focus to it.
        await pilot.click("#prompt")
        await pilot.pause()
        assert app.focused is prompt
        print("[PASS] mouse click focuses the input field")

        app.action_toggle_debug()
        await pilot.pause()
        assert app.focused is prompt
        print("[PASS] debug toggle returns focus to the composer")


def main():
    print("="*72)
    print("RazaAI Step 20.1 Prompt Focus & Input")
    print("="*72)
    asyncio.run(exercise())
    print("="*72)
    print("STEP 20.1 PROMPT FOCUS & INPUT PASSED")
    print("="*72)


if __name__=="__main__":
    main()
