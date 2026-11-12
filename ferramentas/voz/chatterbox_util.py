# Carregamento do Chatterbox (env chatterbox).
# 'ptbr' usa o CÓDIGO OFICIAL da demonstração pt-BR da Resemble (vendor/chatterbox_v3, copiado do Space
# ResembleAI/Chatterbox-Multilingual-TTS-pt-br): o S3Gen v3 e o vocabulário do T3 pt-BR não funcionam
# com o chatterbox-tts 0.1.7 do pip (misturar os dois gera áudio distorcido).
import sys
from pathlib import Path
from comum import MODELOS

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))


def carregar(qual, dispositivo="cuda"):
    """Devolve o modelo pronto. 'ptbr' = fine-tune pt-BR oficial (v3); 'mtl' = multilíngue v2 do pip."""
    if qual == "mtl":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_local(MODELOS / "chatterbox_mtl", dispositivo)
    from chatterbox_v3.tts import ChatterboxTTS
    pasta = MODELOS / "chatterbox_v3_ptbr"
    if not (pasta / ".pronto").exists():
        import shutil
        pasta.mkdir(parents=True, exist_ok=True)
        base, pt = MODELOS / "chatterbox_mtl", MODELOS / "chatterbox_ptbr_src"
        for f in ("ve.pt", "conds.pt"):
            shutil.copyfile(base / f, pasta / f)
        for f in ("grapheme_mtl_merged_expanded_v1.json", "t3_pt_br.safetensors", "s3gen_v3.pt"):
            shutil.copyfile(pt / f, pasta / f)
        (pasta / ".pronto").write_text("ok")
    return ChatterboxTTS.from_local(pasta, dispositivo, t3_filename="t3_pt_br.safetensors", s3gen_filename="s3gen_v3.pt")


def gerar(modelo, texto, ref=None, intensidade=0.5, temperatura=0.8):
    """Gera uma fala e devolve (numpy float32, sr). Mesmos padrões da demonstração oficial (cfg 0.5, temp 0.8)."""
    import numpy as np
    cfg = 0.5 if intensidade <= 0.6 else 0.35
    w = modelo.generate(texto, audio_prompt_path=str(ref) if ref else None,
                        exaggeration=intensidade, cfg_weight=cfg, temperature=temperatura, language_id="pt")
    w = w.squeeze().detach().cpu().numpy() if hasattr(w, "detach") else np.asarray(w).squeeze()
    return w.astype("float32"), modelo.sr
