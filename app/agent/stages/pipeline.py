"""Ordered turn-stage dispatcher introduced in RazaAI ."""
from .context import StageResult


class PrepareTurnStage:
    name = "prepare"
    def run(self, agent, ctx):
        agent._stage_prepare_turn(ctx)
        return StageResult.continue_turn()


class PreflightStage:
    name = "preflight"
    def run(self, agent, ctx):
        content = agent._stage_preflight_reply(ctx)
        return StageResult.complete(content) if content is not None else StageResult.continue_turn()


class EdgeStage:
    name = "edge"
    def run(self, agent, ctx):
        agent._stage_prepare_edge(ctx)
        content = agent._stage_edge_reply(ctx)
        return StageResult.complete(content) if content is not None else StageResult.continue_turn()


class PlaybookStage:
    name = "playbook"
    def run(self, agent, ctx):
        content = agent._stage_playbook(ctx)
        return StageResult.complete(content) if content is not None else StageResult.continue_turn()


class PromptStage:
    name = "prompt"
    def run(self, agent, ctx):
        agent._stage_build_prompt(ctx)
        return StageResult.continue_turn()


class ModelStage:
    name = "model"
    def run(self, agent, ctx):
        return StageResult.complete(agent._stage_model_turn(ctx))


class TurnPipeline:
    """Run the stable priority order. First terminal stage wins."""

    def __init__(self, stages):
        self.stages = tuple(stages)

    @classmethod
    def default(cls):
        return cls((
            PrepareTurnStage(),
            PreflightStage(),
            EdgeStage(),
            PlaybookStage(),
            PromptStage(),
            ModelStage(),
        ))

    def run(self, agent, ctx):
        for stage in self.stages:
            outcome = stage.run(agent, ctx)
            if outcome.handled:
                # Post-turn outcome learning runs on every terminal
                # path (edge, playbook, or model). It must never change the
                # reply: _track_conversation_outcome swallows its errors.
                tracker = getattr(agent, "_track_conversation_outcome", None)
                if callable(tracker):
                    tracker(ctx.user_input, outcome.content)
                return outcome.content
        raise RuntimeError("RazaAI turn pipeline completed without a terminal stage")
