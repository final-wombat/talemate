import pydantic
from openai import AsyncOpenAI

from talemate.client.base import ClientBase
from talemate.client.registry import register


class Defaults(pydantic.BaseModel):
    api_url: str = "http://localhost:1234"
    max_token_length: int = 4096

@register()
class TestClient(ClientBase):
    client_type = "test"

    class Meta(ClientBase.Meta):
        name_prefix: str = "test"
        title: str = "Test"
        defaults: Defaults = Defaults()

    def set_client(self, **kwargs):
        self.client = AsyncOpenAI(base_url=self.api_url + "/v1", api_key="sk-1111")

    def tune_prompt_parameters(self, parameters: dict, kind: str):
        
        """
        Talemate adds a bunch of parameters to the prompt, but not all of them are valid for all clients.
        
        This method is called before the prompt is sent to the client, and it allows the client to remove
        any parameters that it doesn't support.
        """
        
        super().tune_prompt_parameters(parameters, kind)

        keys = list(parameters.keys())

        valid_keys = ["temperature", "top_p"]

        for key in keys:
            if key not in valid_keys:
                del parameters[key]

    async def get_model_name(self):
        
        """
        This should return the name of the model that is being used.
        """
        
        return "Mock test model"

    async def generate(self, prompt: str, parameters: dict, kind: str):
        """
        Generates text from the given prompt and parameters.
        """
        human_message = {"role": "user", "content": prompt.strip()}

        self.log.debug("generate", prompt=prompt[:128] + " ...", parameters=parameters)

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name, messages=[human_message], **parameters
            )

            return response.choices[0].message.content
        except Exception as e:
            self.log.error("generate error", e=e)
            return ""
