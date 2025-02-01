from talemate.agents.base import Agent, AgentAction
from talemate.agents.registry import register
from talemate.events import GameLoopEvent
import talemate.emit.async_signals
from talemate.emit import emit

@register()
class TestAgent(Agent):
    
    agent_type = "test"
    verbose_name = "Test"
    
    def __init__(self, client):
        self.client = client
        self.is_enabled = True
        self.actions = {
            "test": AgentAction(
                enabled=True,
                label="Test",
                description="Test",
            ),
        }
        
    @property
    def enabled(self):
        return self.is_enabled

    @property
    def has_toggle(self):
        return True

    @property
    def experimental(self):
        return True

    def connect(self, scene):
        super().connect(scene)
        talemate.emit.async_signals.get("game_loop").connect(self.on_game_loop)
        
    async def on_game_loop(self, emission: GameLoopEvent):
        """
        Called on the beginning of every game loop
        """

        if not self.enabled:
            return

        emit("status", status="info", message="Annoying you with a test message every game loop.")