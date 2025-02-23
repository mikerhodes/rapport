from typing import Dict, List, Generator
import ollama


class ChatGateway:
    models: List[str]
    model_to_client: Dict[str, object]

    def __init__(self):
        self.models = []
        self.model_to_client = {}

        oc = ollama.Client()
        ollama_models = [model["model"] for model in oc.list()["models"]]
        self.models.extend(ollama_models)
        for m in ollama_models:
            self.model_to_client[m] = oc

    def list(self):
        return self.models

    def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool, num_ctx: int
    ) -> Generator[Dict, None, None]:
        c = self.model_to_client[model]
        response = c.chat(
            model=model,
            messages=messages,
            stream=True,
            options=ollama.Options(
                num_ctx=num_ctx,
            ),
        )
        for chunk in response:
            yield chunk

    def show(self, model: str) -> Dict[str, object]:
        c = self.model_to_client[model]
        return c.show(model)
