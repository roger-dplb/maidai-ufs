"""Cliente da API OpenAI, usado quando MAIDAI_BACKEND=openai (máquina sem GPU).

A chave vem de OPENAI_API_KEY (variável de ambiente ou arquivo .env na raiz do projeto).
OPENAI_BASE_URL, se definida, aponta para outro servidor compatível com a API da OpenAI.
"""
import base64
import io
import json
import math
import sys
from pathlib import Path

from openai import BadRequestError, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

MAX_TOKENS = 16384   # folga para modelos que gastam tokens de raciocínio antes da resposta

_cliente = None
_sem_temperatura = False


def cliente():
    global _cliente
    if _cliente is None:
        _cliente = OpenAI(max_retries=5, timeout=300)
    return _cliente


def chat(mensagens, modelo=None, json=False):
    """Uma chamada de chat com temperature=0 (resultado repetível). Se o modelo não aceitar
    temperature, repete sem ela e não envia mais nas chamadas seguintes."""
    global _sem_temperatura
    args = {"model": modelo or config.OPENAI_MODELO, "messages": mensagens, "max_completion_tokens": MAX_TOKENS}
    if json:
        args["response_format"] = {"type": "json_object"}
    if not _sem_temperatura:
        args["temperature"] = 0
    try:
        r = cliente().chat.completions.create(**args)
    except BadRequestError as e:
        if "temperature" not in args or "temperature" not in str(e):
            raise
        if not _sem_temperatura:
            print("[OpenAI] O modelo não aceita temperature=0; usando a temperatura padrão do modelo.")
        _sem_temperatura = True
        args.pop("temperature")
        r = cliente().chat.completions.create(**args)
    return (r.choices[0].message.content or "").strip()


class Visao:
    """Mesma interface do modelo do Moondream (query(image, pergunta) -> {"answer": ...})."""

    def __init__(self, modelo=None):
        self.modelo = modelo or config.OPENAI_MODELO_VISAO
        self._ultima = (None, None)   # a mesma imagem recebe várias perguntas: codifica uma vez só

    def _data_url(self, image):
        if self._ultima[0] is not image:
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=90)
            self._ultima = (image, "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
        return self._ultima[1]

    def query(self, image, pergunta):
        conteudo = [{"type": "text", "text": pergunta},
                    {"type": "image_url", "image_url": {"url": self._data_url(image), "detail": "high"}}]
        return {"answer": chat([{"role": "user", "content": conteudo}], modelo=self.modelo)}


def traduzir(dados):
    """Traduz para português os textos de um dict (mesmas chaves). Devolve {} se a resposta não for JSON."""
    pedido = ("Traduza para o português do Brasil os valores de texto deste JSON. Mantenha as chaves, "
              "nomes próprios, números, placas e textos entre aspas exatamente como estão. "
              "Responda apenas com o JSON traduzido.\n" + json.dumps(dados, ensure_ascii=False))
    try:
        r = json.loads(chat([{"role": "user", "content": pedido}], json=True))
    except json.JSONDecodeError:
        return {}
    return r if isinstance(r, dict) else {}


def transcrever(caminho, prompt=None):
    """Transcrição com timestamps por trecho, no formato de saída do whisper-timestamped
    (segments[].start/end/text/no_speech_prob/compression_ratio/confidence)."""
    args = {"model": config.OPENAI_MODELO_AUDIO, "language": "pt", "temperature": 0,
            "response_format": "verbose_json", "timestamp_granularities": ["segment"]}
    if prompt:
        args["prompt"] = prompt
    with open(caminho, "rb") as f:
        res = cliente().audio.transcriptions.create(file=f, **args).model_dump()
    segmentos = []
    for s in res.get("segments") or []:
        segmentos.append({
            "start": s.get("start", 0), "end": s.get("end", 0), "text": s.get("text", ""),
            "no_speech_prob": s.get("no_speech_prob") or 0,
            "compression_ratio": s.get("compression_ratio") or 0,
            # a API não dá confiança por palavra; exp(avg_logprob) é a probabilidade média dos tokens
            "confidence": math.exp(s["avg_logprob"]) if s.get("avg_logprob") is not None else 0,
            "words": [],
        })
    return {"text": res.get("text", ""), "segments": segmentos}
