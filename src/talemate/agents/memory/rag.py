from typing import TYPE_CHECKING
import structlog
from talemate.agents.base import (
    AgentAction,
    AgentActionConfig,
)
from talemate.emit import emit
import talemate.instance as instance

if TYPE_CHECKING:
    from talemate.tale_mate import Character

__all__ = ["MemoryRAGMixin"]

log = structlog.get_logger()

class MemoryRAGMixin:
    
    @classmethod
    def add_actions(cls, agent):
        
        agent.actions["use_long_term_memory"] = AgentAction(
            enabled=True,
            container=True,
            can_be_disabled=True,
            icon="mdi-brain",
            label="Long Term Memory",
            description="Will augment the context with long term memory based on similarity queries.",
            config={
                "retrieval_method": AgentActionConfig(
                    type="text",
                    label="Context Retrieval Method",
                    description="How relevant context is retrieved from the long term memory.",
                    value="direct",
                    choices=[
                        {
                            "label": "Context queries based on recent progress (fast)",
                            "value": "direct",
                        },
                        {
                            "label": "Context queries generated by AI",
                            "value": "queries",
                        },
                        {
                            "label": "AI compiled question and answers (slow)",
                            "value": "questions",
                        }
                    ],
                ),
                "number_of_queries": AgentActionConfig(
                    type="number",
                    label="Number of Queries",
                    description="The number of queries to use when retrieving context from the long term memory.",
                    value=3,
                    min=1,
                    max=10,
                    step=1,
                ),
                "answer_length": AgentActionConfig(
                    type="text",
                    label="Answer Length",
                    description="The maximum length of long term memory response.",
                    value="512",
                    choices=[
                        {"label": "Short (256)", "value": "256"},
                        {"label": "Medium (512)", "value": "512"},
                        {"label": "Long (1024)", "value": "1024"},
                    ]
                ),
                "cache": AgentActionConfig(
                    type="bool",
                    label="Cache",
                    description="Cache the long term memory for faster retrieval.",
                    note="This is a cross-agent cache, assuming they use the same options.",
                    value=True
                )
            },
        )
        
    # config property helpers
    
    @property
    def long_term_memory_enabled(self):
        return self.actions["use_long_term_memory"].enabled
    
    @property
    def long_term_memory_retrieval_method(self):
        return self.actions["use_long_term_memory"].config["retrieval_method"].value

    @property
    def long_term_memory_number_of_queries(self):
        return self.actions["use_long_term_memory"].config["number_of_queries"].value
    
    @property
    def long_term_memory_answer_length(self):
        return int(self.actions["use_long_term_memory"].config["answer_length"].value)
    
    @property
    def long_term_memory_cache(self):
        return self.actions["use_long_term_memory"].config["cache"].value
    
    @property
    def long_term_memory_cache_key(self):
        """
        Build the key from the various options
        """
        
        parts = [
            self.long_term_memory_retrieval_method,
            self.long_term_memory_number_of_queries,
            self.long_term_memory_answer_length
        ]
        
        return "-".join(map(str, parts))
    
    
    def connect(self, scene):
        super().connect(scene)
        
        # new scene, reset cache
        scene.rag_cache = {}
    
    # methods
    
    async def rag_set_cache(self, content:list[str]):
        self.scene.rag_cache[self.long_term_memory_cache_key] = {
            "content": content,
            "fingerprint": self.scene.history[-1].fingerprint if self.scene.history else 0 
        }
        
    async def rag_get_cache(self) -> list[str] | None:
        
        if not self.long_term_memory_cache:
            return None
        
        fingerprint = self.scene.history[-1].fingerprint if self.scene.history else 0
        cache = self.scene.rag_cache.get(self.long_term_memory_cache_key)
        
        if cache and cache["fingerprint"] == fingerprint:
            return cache["content"]
        
        return None
            
    async def rag_build(
        self, 
        character: "Character" = None, 
        prompt: str = "",
        sub_instruction: str = "",
    ) -> list[str]:
        """
        Builds long term memory to be inserted into a prompt
        """

        if not self.long_term_memory_enabled:
            return []
        
        cached = await self.rag_get_cache()
        
        if cached:
            log.debug(f"Using cached long term memory", agent=self.agent_type, key=self.long_term_memory_cache_key)
            return cached

        memory_context = ""
        retrieval_method = self.long_term_memory_retrieval_method
        
        if not sub_instruction:
            if character:
                sub_instruction = f"continue the scene as {character.name}"
            else:
                sub_instruction = "continue the scene"
            
        if retrieval_method != "direct":
            world_state = instance.get_agent("world_state")
            
            if not prompt:
                prompt = self.scene.context_history(
                    keep_director=False,
                    budget=int(self.client.max_token_length * 0.75),
                )
                
            if isinstance(prompt, list):
                prompt = "\n".join(prompt)
                
            log.debug(
                "memory_rag_mixin.build_prompt_default_memory",
                direct=False,
                version=retrieval_method,
            )

            if retrieval_method == "questions":
                memory_context = (
                    await world_state.analyze_text_and_extract_context(
                        prompt, sub_instruction,
                        include_character_context=True,
                        response_length=self.long_term_memory_answer_length,
                        num_queries=self.long_term_memory_number_of_queries
                    )
                ).split("\n")
            elif retrieval_method == "queries":
                memory_context = (
                    await world_state.analyze_text_and_extract_context_via_queries(
                        prompt, sub_instruction,
                        include_character_context=True,
                        response_length=self.long_term_memory_answer_length,
                        num_queries=self.long_term_memory_number_of_queries
                        
                    )
                )

        else:
            history = list(map(str, self.scene.collect_messages(max_iterations=3)))
            log.debug(
                "memory_rag_mixin.build_prompt_default_memory",
                history=history,
                direct=True,
            )
            memory = instance.get_agent("memory")
            context = await memory.multi_query(history, max_tokens=500, iterate=5)
            memory_context = context

        await self.rag_set_cache(memory_context)

        return memory_context