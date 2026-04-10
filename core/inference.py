import logging
from typing import Any, Callable, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MultiModelData(BaseModel):
    modality: Literal['image', 'audio', 'video']
    data: Any
    capture: Callable[..., Any]


class BaseInferenceModel:
    base_url: str
    api_key: str = ''
    model: str

    def __init__(self, **data):
        self.base_url = data.get('base_url', '')
        self.api_key = data.get('api_key', '')
        self.model = data.get('model', '')
        self.config = {k: v for k, v in data.items() if k not in ('base_url', 'api_key', 'model')}

    def infer(self, prompt: str, multi_model_data: list[MultiModelData] | None = None):
        return ''


class OpenAI(BaseInferenceModel):

    def __init__(self, **data):
        super().__init__(**data)
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def infer(self, prompt: str, multi_model_data: list[MultiModelData] | None = None):
        try:
            multi_model_data = multi_model_data or []
            response = self.client.responses.create(model=self.model, input=prompt)
            return response.output_text
        except Exception:
            logger.warning('openai inference failed for model=%s', self.model, exc_info=True)
            return ''


class MLX(BaseInferenceModel):

    def __init__(self, **data):
        super().__init__(**data)
        from mlx_vlm import load
        self.model, self.processor = load(self.model)


    def infer(self, prompt: str, multi_model_data: list[MultiModelData] | None = None):
        try:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template
            
            image = [d.data for d in (multi_model_data or []) if d.modality == 'image']
            audio = [d.data for d in (multi_model_data or []) if d.modality == 'audio']
            video = [d.data for d in (multi_model_data or []) if d.modality == 'video']
            
            formatted_prompt = apply_chat_template(
                self.processor, self.model.config, 
                prompt, 
                num_images=len(image),
                num_audios=len(audio),
                num_videos=len(video),
                chat_template_kwargs = {"enable_thinking": True},
            )
            output = generate(self.model, self.processor, formatted_prompt,
                              image=image,
                              video=video,
                              audio=audio, 
                              verbose=False,
                              max_tokens=2000,
                              temperature=1.0,
                              top_p=0.95,
                              top_k=64,
                              )
            return output
        except Exception:
            logger.warning('mlx inference failed for model=%s', self.model, exc_info=True)
            return ''

class LCPP(BaseInferenceModel):
    def __init__(self, **data):
        super().__init__(**data)
        from llama_cpp import Llama
        self.client = Llama(model_path=self.model, device='mps')


    def infer(self, prompt: str, multi_model_data: list[MultiModelData] | None = None):
        try:
            output = self.client.create_completion(prompt=prompt)
            result = output['choices'][0]['text']
            return result
        except Exception:
            logger.warning('lcpp inference failed for model=%s', self.model, exc_info=True)
            return ''

class Transformers(BaseInferenceModel):
    def __init__(self, **data):
        super().__init__(**data)

        from transformers import pipeline
        self.pipeline = pipeline(model=self.model)

    
    def infer(self, prompt: str, multi_model_data: list[MultiModelData] | None = None):
        try:
            return self.pipeline(prompt)
        except Exception:
            logger.warning('transformers inference failed for model=%s', self.model, exc_info=True)
            return ''


def get_inference_model(model_name: str, **args) -> BaseInferenceModel:
    provider, model = model_name.split('/', 1)
    if provider == 'openai':
        return OpenAI(base_url='https://api.openai.com/v1', api_key=args.get('api_key', ''), model=model, **args)
    if provider == 'lms':
        return OpenAI(base_url='http://127.0.0.1:1234/v1', model=model, **args)
    if provider == 'mlx':
        return MLX(model=model, **args)
    if provider == 'transformers':
        return Transformers(model=model, **args)
    if provider == 'lcpp':
        return LCPP(model=model, **args)
    return BaseInferenceModel(model=model, **args)

