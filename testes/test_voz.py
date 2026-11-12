# Conferência de leitura: número em algarismo (Whisper) e por extenso (roteiro) contam igual.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas" / "voz"))
from comum import _extenso, wer


def test_extenso():
    assert _extenso(1998) == "mil novecentos e noventa e oito"
    assert _extenso(2026) == "dois mil e vinte e seis"
    assert _extenso(100) == "cem" and _extenso(101) == "cento e um" and _extenso(40000) == "quarenta mil"


def test_wer_numeros():
    assert wer("Aquela ali é de mil novecentos e noventa e oito.", "Aquela ali é de 1998.") == 0
    assert wer("quarenta mil reais", "40.000 reais") == 0
