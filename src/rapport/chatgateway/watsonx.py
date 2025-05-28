import logging
import os
from typing import (
    Dict,
    Generator,
    List,
    Optional,
)

import ibm_watsonx_ai as wai
import ibm_watsonx_ai.foundation_models as waifm
from ibm_watsonx_ai.wml_client_error import WMLClientError

from rapport.chatmodel import (
    MessageList,
)
from rapport.tools import Tool

from .common import prepare_messages_for_model
from .types import (
    ChatAdaptor,
    ChatException,
    FinishReason,
    MessageChunk,
    MissingEnvVarException,
)

logger = logging.getLogger(__name__)


class WatsonxAdaptor(ChatAdaptor):
    c: Optional[wai.APIClient]
    model_cache: Dict[str, waifm.ModelInference]
    models: List[str]
    apikey: str

    def __init__(self):
        self.c = None
        self.model_cache = {}

        if k := os.environ.get("WATSONX_IAM_API_KEY"):
            self.apikey = k
        else:
            raise MissingEnvVarException("WATSONX_IAM_API_KEY")

        if k := os.environ.get("WATSONX_PROJECT"):
            self.project_id = k
        else:
            raise MissingEnvVarException("WATSONX_PROJECT")

        if k := os.environ.get("WATSONX_URL"):
            self.url = k
        else:
            raise MissingEnvVarException("WATSONX_URL")

        # don't support this for now
        self.space_id = None

        # curate a decent set of models
        self.models = [
            "ibm/granite-3-8b-instruct",
            "meta-llama/llama-3-3-70b-instruct",
            "mistralai/mistral-medium-2505",
        ]

    def _client(self):
        if self.c:
            return self.c

        credentials = wai.Credentials(
            url=self.url,
            api_key=self.apikey,
        )
        self.c = wai.APIClient(credentials)
        return self.c

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        return False

    def _model_inference(self, model: str) -> waifm.ModelInference:
        if m := self.model_cache.get(model):
            return m

        params = {
            "time_limit": 10000,
            "max_tokens": 40960,
        }
        verify = True
        fmodel = waifm.ModelInference(
            model_id=model,
            api_client=self._client(),
            params=params,
            project_id=self.project_id,
            space_id=self.space_id,
            verify=verify,
        )
        self.model_cache[model] = fmodel
        return fmodel

    def chat(
        self,
        model: str,
        messages: MessageList,
        tools: List[Tool],
    ) -> Generator[MessageChunk, None, None]:
        messages_content = prepare_messages_for_model(messages)
        fmodel = self._model_inference(model)
        try:
            stream_response = fmodel.chat_stream(messages=messages_content)
            for chunk in stream_response:
                content = ""
                input_tokens = None
                output_tokens = None
                finish_reason = None
                if ch := chunk.get("choices"):
                    content = ch[0]["delta"].get("content", "")
                    match ch[0]["finish_reason"]:
                        case "stop":
                            finish_reason = FinishReason.Stop
                        case "length":
                            finish_reason = FinishReason.Length
                        case None:
                            finish_reason = None
                        case _:
                            finish_reason = FinishReason.Other
                if chunk.get("usage"):
                    input_tokens = chunk["usage"]["total_tokens"]
                    output_tokens = 0  # TODO fix this per watsonx schema
                mc = MessageChunk(
                    content=content,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=finish_reason,
                    tool_call=None,
                )
                yield mc
        except WMLClientError as ex:
            raise ChatException(str(ex))
