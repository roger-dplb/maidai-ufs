"""Interface web (Streamlit) da pipeline, para rodar em VM sem tela.

    streamlit run src/demo/app_web.py --server.address 0.0.0.0 --server.port 8501

Cada análise ganha uma pasta própria em jobs/<data>_<id>/ (evidências enviadas + saídas), então
uma análise não apaga a outra. Não há login: use só em rede interna.
"""
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import pipeline  # noqa: E402

JOBS_DIR = config.PROJECT_DIR / "jobs"
EXTENSOES = ["jpg", "jpeg", "png", "webp", "bmp", "gif", "heic", "tif", "tiff",
             "mp3", "wav", "ogg", "opus", "m4a", "aac", "amr", "flac", "wma", "txt", "csv"]

st.set_page_config(page_title="maidai-ufs", layout="wide")


def salvar_evidencias(arquivos, contexto):
    """Grava os uploads numa pasta nova. Devolve (pasta, caminho do CSV do IPED)."""
    pasta = JOBS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    pasta.mkdir(parents=True)
    filelist = pasta / "Filelist.csv"   # se não vier CSV, o caminho não existe e a pasta é varrida
    for arq in arquivos:
        nome = Path(arq.name).name
        if nome.lower().endswith(".txt"):
            nome = "text_message.txt"   # nome que o llama_vllm.py procura
        elif nome.lower().endswith(".csv"):
            nome = filelist.name
        (pasta / nome).write_bytes(arq.getvalue())
    if contexto.strip():
        (pasta / "contexto_filtro.txt").write_text(contexto.strip(), encoding="utf-8")
    return pasta, filelist


def mostrar_resultado(pasta):
    abas = st.tabs(["Relatório", "Entidades", "Eventos", "Imagens", "Áudios"])
    relatorio = pipeline.formatar_relatorio(pasta)
    with abas[0]:
        st.markdown(relatorio)
    with abas[1]:
        st.json(pipeline.ler_json(pasta, "entities.json") or {})
    with abas[2]:
        st.json(pipeline.ler_json(pasta, "events.json") or {})
    with abas[3]:
        st.text(pipeline.texto_imagens(pasta) or "Nenhuma imagem analisada.")
    with abas[4]:
        st.text(pipeline.texto_audios(pasta) or "Nenhum áudio transcrito.")

    col1, col2 = st.columns(2)
    col1.download_button("Baixar relatório (.txt)", relatorio, file_name="relatorio_forense_final.txt")
    consolidado = pipeline.ler_json(pasta, "consolidado.json")
    if consolidado:
        col2.download_button("Baixar consolidado (.json)", json.dumps(consolidado, ensure_ascii=False, indent=2),
                             file_name="consolidado.json")


st.title("Pipeline forense multimodal")
st.caption(f"Backend: {config.BACKEND}"
           + (f" ({config.OPENAI_MODELO} / {config.OPENAI_MODELO_AUDIO})" if config.usa_openai() else ""))

with st.form("analise"):
    arquivos = st.file_uploader("Evidências: imagens, áudios, conversa (.txt) e CSV do IPED (opcional)",
                                type=EXTENSOES, accept_multiple_files=True)
    contexto = st.text_area("Contexto do perito (opcional)")
    enviar = st.form_submit_button("Analisar")

if enviar:
    if not arquivos:
        st.warning("Envie pelo menos um arquivo.")
    else:
        pasta, filelist = salvar_evidencias(arquivos, contexto)
        linhas = []
        with st.status("Analisando...", expanded=True) as status:
            painel = st.empty()

            def log(linha):
                linhas.append(linha)
                painel.code("\n".join(linhas[-40:]))

            ok = pipeline.executar_pipeline(pasta, filelist, log=log)
            status.update(label="Análise concluída" if ok else "Análise terminou sem relatório",
                          state="complete" if ok else "error", expanded=not ok)
        st.session_state["pasta"] = str(pasta)

if st.session_state.get("pasta"):
    mostrar_resultado(Path(st.session_state["pasta"]))
