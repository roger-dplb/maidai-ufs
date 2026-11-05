"""Interface web (Streamlit) da pipeline, para rodar em VM sem tela.

    streamlit run src/demo/app_web.py --server.address 0.0.0.0 --server.port 8501

Cada análise ganha uma pasta própria em jobs/<data>_<id>/ (evidências enviadas + saídas), então
uma análise não apaga a outra. Não há login: use só em rede interna.

A tela é pensada para quem não é técnico: não cita modelos, fornecedores nem arquivos internos.
O log técnico completo vai para a saída padrão (terminal ou docker logs).
"""
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

# Marcadores das etapas no log da pipeline -> (título do quadro de progresso, item da lista)
# Fotos e áudios podem rodar ao mesmo tempo, então dividem o mesmo título.
ETAPAS = {"=== ETAPA 1": ("Analisando as fotos e os áudios...", "Analisando as fotos..."),
          "=== ETAPA 2": ("Analisando as fotos e os áudios...", "Transcrevendo os áudios..."),
          "=== ETAPA 3": ("Cruzando as evidências e redigindo o relatório...",
                          "Cruzando as evidências e redigindo o relatório...")}
TIPOS_FOTO = {"photo": "Foto", "screenshot": "Captura de tela", "document": "Documento", "other": "Outro"}
ITENS_FOTO = {"weapon": "Arma", "drugs": "Drogas", "cash": "Dinheiro", "package": "Pacote ou caixa",
              "context": "Relacionado ao contexto informado"}
RELEVANCIA = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}

st.set_page_config(page_title="Análise Forense de Evidências", layout="wide")


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


def _rotulo(valor):
    return str(valor or "").replace("_", " ").capitalize()


def aba_pessoas(pasta):
    entidades = (pipeline.ler_json(pasta, "entities.json") or {}).get("entities", [])
    if not entidades:
        st.info("Nenhuma pessoa, local ou objeto identificado.")
        return
    st.dataframe([{"Nome": e.get("nome_ou_alias"), "Tipo": _rotulo(e.get("tipo")),
                   "Também chamado de": ", ".join(e.get("aliases", [])),
                   "Aparece em": ", ".join(e.get("arquivos", [])),
                   "Relevância": RELEVANCIA.get(e.get("relevancia"), "")} for e in entidades],
                 hide_index=True, use_container_width=True)


def aba_acontecimentos(pasta):
    eventos = (pipeline.ler_json(pasta, "events.json") or {}).get("eventos", [])
    if not eventos:
        st.info("Nenhum acontecimento identificado.")
        return
    st.dataframe([{"Tipo": _rotulo(v.get("tipo")), "O que aconteceu": v.get("descricao"),
                   "Onde foi encontrado": v.get("arquivo"), "Quando": v.get("timestamp") or "",
                   "Trecho original": v.get("trecho_literal")} for v in eventos],
                 hide_index=True, use_container_width=True)


def aba_fotos(pasta):
    fotos = pipeline.ler_json(pasta, "visual.json") or []
    if not fotos:
        st.info("Nenhuma foto analisada.")
        return
    for f in fotos:
        col_img, col_txt = st.columns([1, 2])
        caminho = pasta / str(f.get("name"))
        if caminho.is_file():
            col_img.image(str(caminho), use_container_width=True)
        with col_txt:
            st.markdown(f"**{f.get('name')}** · {TIPOS_FOTO.get(f.get('tipo_imagem'), 'Imagem')}")
            if f.get("erro"):
                st.warning("Não foi possível analisar esta imagem. Confira manualmente.")
                continue
            descricao = f.get("descricao_cena_pt") or f.get("descricao_cena")
            if descricao:
                st.write(descricao)
            for chave, texto in (f.get("indicios_pt") or f.get("indicios") or {}).items():
                st.warning(f"**Ponto de atenção — {ITENS_FOTO.get(chave, _rotulo(chave))}:** {texto}")
            if f.get("visible_text"):
                st.markdown("**Texto na imagem:**")
                st.text(f["visible_text"])
            if f.get("gps"):
                st.markdown(f"**Localização registrada na foto:** {f['gps']['latitude']}, {f['gps']['longitude']}")
        st.divider()


def mostrar_resultado(pasta):
    abas = st.tabs(["Relatório", "Pessoas e locais", "Acontecimentos", "Fotos", "Áudios"])
    relatorio = pipeline.formatar_relatorio(pasta)
    with abas[0]:
        st.markdown(relatorio)
        st.download_button("Baixar relatório", relatorio, file_name="relatorio_forense.txt")
    with abas[1]:
        aba_pessoas(pasta)
    with abas[2]:
        aba_acontecimentos(pasta)
    with abas[3]:
        aba_fotos(pasta)
    with abas[4]:
        st.text(pipeline.texto_audios(pasta) or "Nenhum áudio transcrito.")


st.title("Análise Forense de Evidências")
st.caption("Envie fotos, áudios e conversas. O sistema identifica pessoas, locais e acontecimentos "
           "e monta um relatório para revisão do perito.")

with st.form("analise"):
    arquivos = st.file_uploader("Evidências: fotos, áudios, conversa (.txt) e planilha do IPED (opcional)",
                                type=EXTENSOES, accept_multiple_files=True)
    contexto = st.text_area("Informações do caso (opcional)",
                            placeholder="Ex.: suspeita de entrega de material ilícito no Parque da Sementeira")
    enviar = st.form_submit_button("Analisar")

if enviar:
    if not arquivos:
        st.warning("Envie pelo menos um arquivo.")
    else:
        pasta, filelist = salvar_evidencias(arquivos, contexto)
        with st.status("Preparando as evidências...", expanded=True) as status:

            def log(linha):
                print(linha, flush=True)   # log técnico completo fica no terminal / docker logs
                for marcador, (titulo, item) in ETAPAS.items():
                    if linha.startswith(marcador):
                        status.update(label=titulo)
                        st.write(item)

            try:
                ok = pipeline.executar_pipeline(pasta, filelist, log=log)
            except Exception as e:
                print(f"[ERRO] {type(e).__name__}: {e}", flush=True)
                ok = False
            if ok:
                status.update(label="Análise concluída", state="complete", expanded=False)
            else:
                status.update(label="Não foi possível concluir a análise", state="error")
                st.write("Confira se os arquivos enviados abrem normalmente e tente de novo. "
                         "Se o problema continuar, acione o suporte técnico.")
        st.session_state["pasta"] = str(pasta) if ok else None

if st.session_state.get("pasta"):
    mostrar_resultado(Path(st.session_state["pasta"]))
