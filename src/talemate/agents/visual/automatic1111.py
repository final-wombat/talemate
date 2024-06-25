import base64
import io

import httpx
import structlog
from PIL import Image

from talemate.agents.base import (
    Agent,
    AgentAction,
    AgentActionConditional,
    AgentActionConfig,
    AgentDetail,
    set_processing,
)

from .handlers import register
from .schema import RenderSettings, Resolution
from .style import STYLE_MAP, Style

log = structlog.get_logger("talemate.agents.visual.automatic1111")


@register(backend_name="automatic1111", label="AUTOMATIC1111")
class Automatic1111Mixin:

    automatic1111_default_render_settings = RenderSettings()

    EXTEND_ACTIONS = {
        "automatic1111": AgentAction(
            enabled=True,
            container=True,
            condition=AgentActionConditional(
                attribute="_config.config.backend", value="automatic1111"
            ),
            icon="mdi-server-outline",
            label="AUTOMATIC1111",
            description="Settings for the currently selected AUTOMATIC1111 backend.",
            config={
                "api_url": AgentActionConfig(
                    type="text",
                    value="http://localhost:7860",
                    label="API URL",
                    description="The URL of the backend API",
                ),
                "steps": AgentActionConfig(
                    type="number",
                    value=40,
                    label="Steps",
                    min=5,
                    max=150,
                    step=1,
                    description="number of render steps",
                ),
                "model_type": AgentActionConfig(
                    type="text",
                    value="sdxl",
                    choices=[
                        {"value": "sdxl", "label": "SDXL"},
                        {"value": "sd15", "label": "SD1.5"},
                    ],
                    label="Model Type",
                    description="Right now just differentiates between sdxl and sd15 - affect generation resolution",
                ),
            },
        )
    }

    @property
    def automatic1111_render_settings(self):
        if self.actions["automatic1111"].enabled:
            return RenderSettings(
                steps=self.actions["automatic1111"].config["steps"].value,
                type_model=self.actions["automatic1111"].config["model_type"].value,
            )
        else:
            return self.automatic1111_default_render_settings

    async def automatic1111_generate(self, prompt: Style, format: str):
        url = self.api_url
        resolution = self.resolution_from_format(
            format, self.automatic1111_render_settings.type_model
        )
        render_settings = self.automatic1111_render_settings
        payload = {
            "prompt": prompt.positive_prompt,
            "negative_prompt": prompt.negative_prompt,
            "steps": render_settings.steps,
            "width": resolution.width,
            "height": resolution.height,
        }

        log.info("automatic1111_generate", payload=payload, url=url)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{url}/sdapi/v1/txt2img", json=payload, timeout=90
            )

        r = response.json()

        # image = Image.open(io.BytesIO(base64.b64decode(r['images'][0])))
        # image.save('a1111-test.png')

        #'log.info("automatic1111_generate", saved_to="a1111-test.png")

        for image in r["images"]:
            await self.emit_image(image)

    async def automatic1111_ready(self) -> bool:
        """
        Will send a GET to /sdapi/v1/memory and on 200 will return True
        """

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=f"{self.api_url}/sdapi/v1/memory", timeout=2
            )
            return response.status_code == 200
