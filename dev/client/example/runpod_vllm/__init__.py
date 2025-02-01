"""
An attempt to write a client against the runpod serverless vllm worker.

This is close to functional, but since runpod serverless gpu availability is currently terrible, i have
been unable to properly test it.

Putting it here for now since i think it makes a decent example of how to write a client against a new service.
"""

import pydantic
import structlog
import runpod
import asyncio
import aiohttp
from talemate.client.base import ClientBase, ExtraField
from talemate.client.registry import register
from talemate.emit import emit
from talemate.config import Client as BaseClientConfig

log = structlog.get_logger("talemate.client.runpod_vllm")

class Defaults(pydantic.BaseModel):
    max_token_length: int = 4096
    model: str = ""
    runpod_id: str = ""
    
class ClientConfig(BaseClientConfig):
    runpod_id: str = ""

@register()
class RunPodVLLMClient(ClientBase):
    client_type = "runpod_vllm"
    conversation_retries = 5
    config_cls = ClientConfig

    class Meta(ClientBase.Meta):
        title: str = "Runpod VLLM"
        name_prefix: str = "Runpod VLLM"
        enable_api_auth: bool = True
        manual_model: bool = True
        defaults: Defaults = Defaults()
        extra_fields: dict[str, ExtraField] = {
            "runpod_id": ExtraField(
                name="runpod_id",
                type="text",
                label="Runpod ID",
                required=True,
                description="The Runpod ID to connect to.",
            )
        }


    def __init__(self, model=None, runpod_id=None, **kwargs):
        self.model_name = model
        self.runpod_id = runpod_id
        super().__init__(**kwargs)

    @property
    def experimental(self):
        return False


    def set_client(self, **kwargs):
        log.debug("set_client", kwargs=kwargs, runpod_id=self.runpod_id)
        self.runpod_id = kwargs.get("runpod_id", self.runpod_id)
        
        
    def tune_prompt_parameters(self, parameters: dict, kind: str):
        super().tune_prompt_parameters(parameters, kind)

        keys = list(parameters.keys())

        valid_keys = ["temperature", "top_p", "max_tokens"]

        for key in keys:
            if key not in valid_keys:
                del parameters[key]

    async def get_model_name(self):
        return self.model_name

    async def generate(self, prompt: str, parameters: dict, kind: str):
        """
        Generates text from the given prompt and parameters.
        """
        prompt = prompt.strip()

        self.log.debug("generate", prompt=prompt[:128] + " ...", parameters=parameters)

        try:
            
            async with aiohttp.ClientSession() as session:
                endpoint = runpod.AsyncioEndpoint(self.runpod_id, session)
                
                run_request = await endpoint.run({
                    "input": {
                        "prompt": prompt,   
                    }
                    #"parameters": parameters
                })
                
                while (await run_request.status()) not in ["COMPLETED", "FAILED", "CANCELLED"]:
                    status = await run_request.status()
                    log.debug("generate", status=status)
                    await asyncio.sleep(0.1)
                    
                status = await run_request.status()
                
                log.debug("generate", status=status)
                    
                response = await run_request.output()
                
                log.debug("generate", response=response)
                
                return response["choices"][0]["tokens"][0]
            
        except Exception as e:
            self.log.error("generate error", e=e)
            emit(
                "status", message="Error during generation (check logs)", status="error"
            )
            return ""

    def reconfigure(self, **kwargs):
        if kwargs.get("model"):
            self.model_name = kwargs["model"]
        if "runpod_id" in kwargs:
            self.api_auth = kwargs["runpod_id"]
        log.warning("reconfigure", kwargs=kwargs)
        self.set_client(**kwargs)
