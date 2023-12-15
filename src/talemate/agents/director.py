from __future__ import annotations

import asyncio
import re
import random
import structlog
from typing import TYPE_CHECKING, Callable, List, Optional, Union

import talemate.util as util
from talemate.emit import wait_for_input, emit
import talemate.emit.async_signals
from talemate.prompts import Prompt
from talemate.scene_message import NarratorMessage, DirectorMessage
from talemate.automated_action import AutomatedAction
import talemate.automated_action as automated_action
from talemate.agents.conversation import ConversationAgentEmission
from .registry import register
from .base import set_processing, AgentAction, AgentActionConfig, Agent
from talemate.events import GameLoopEvent, GameLoopActorIterEvent

if TYPE_CHECKING:
    from talemate import Actor, Character, Player, Scene

log = structlog.get_logger("talemate")

@register()
class DirectorAgent(Agent):
    agent_type = "director"
    verbose_name = "Director"
    
    def __init__(self, client, **kwargs):
        self.is_enabled = False
        self.client = client
        self.next_direct = 0
        self.actions = {
            "direct": AgentAction(enabled=True, label="Direct", description="Will attempt to direct the scene. Runs automatically after AI dialogue (n turns).", config={
                "turns": AgentActionConfig(type="number", label="Turns", description="Number of turns to wait before directing the sceen", value=5, min=1, max=100, step=1),
                "prompt": AgentActionConfig(type="text", label="Instructions", description="Instructions to the director", value="", scope="scene")
            }),
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
        talemate.emit.async_signals.get("agent.conversation.before_generate").connect(self.on_conversation_before_generate)
        talemate.emit.async_signals.get("game_loop_actor_iter").connect(self.on_player_dialog)
        
    async def on_conversation_before_generate(self, event:ConversationAgentEmission):
        log.info("on_conversation_before_generate", director_enabled=self.enabled)
        if not self.enabled:
            return
        
        await self.direct(event.character)
    
    async def on_player_dialog(self, event:GameLoopActorIterEvent):
    
        if not self.enabled:
            return
        
        if not self.scene.game_state.has_scene_instructions:
            return

        if not event.actor.character.is_player:
            return

        await self.direct(None)
        
    async def direct(self, character: Character):
        
        if not self.actions["direct"].enabled:
            return
        
        prompt = self.actions["direct"].config["prompt"].value
        
        # TODO: old way, will be replaced with game_state.director_instructions
        if not prompt and character:
            log.info("direct_scene", skip=True, prompt=prompt)
            return
        
        always_direct = (not self.scene.npc_character_names)
        
        if self.next_direct % self.actions["direct"].config["turns"].value != 0 or self.next_direct == 0:
            if not always_direct:
                log.info("direct_scene", skip=True, next_direct=self.next_direct)
                self.next_direct += 1
                return
            
        self.next_direct = 0
        
        await self.direct_scene(character, prompt)
        
    @set_processing
    async def direct_scene(self, character: Character, prompt:str):
        
        if not character and self.scene.game_state.game_won:
            # we are not directing a character, and the game has been won
            # so we don't need to direct the scene any further
            return
        
        response = await Prompt.request("director.direct-scene", self.client, "director", vars={
            "max_tokens": self.client.max_token_length,
            "scene": self.scene,
            "prompt": prompt,
            "character": character,
            "player_character": self.scene.get_player_character(),
            "game_state": self.scene.game_state,
        })
        
        if "#" in response:
            response = response.split("#")[0]
        
        log.info("direct_scene", character=character, prompt=prompt, response=response)
        
        if character:
            response = response.strip().split("\n")[0].strip()
            response += f" (current story goal: {prompt})"
            message = DirectorMessage(response, source=character.name)
            emit("director", message, character=character)
            self.scene.push_history(message)
        else:
            response = util.strip_partial_sentences(response).strip()
            response = response.replace('*','').strip()
            
            if not response:
                return
            
            response = f"*{response}*"
            message = NarratorMessage(response, source="__director__")
            emit("narrator", message)
            
            self.scene.push_history(message)        

        
    def inject_prompt_paramters(self, prompt_param: dict, kind: str, agent_function_name: str):
        log.debug("inject_prompt_paramters", prompt_param=prompt_param, kind=kind, agent_function_name=agent_function_name)
        character_names = [f"\n{c.name}:" for c in self.scene.get_characters()]
        if prompt_param.get("extra_stopping_strings") is None:
            prompt_param["extra_stopping_strings"] = []
        prompt_param["extra_stopping_strings"] += character_names + ["#"]
        
    def allow_repetition_break(self, kind: str, agent_function_name: str, auto:bool=False):
        return True