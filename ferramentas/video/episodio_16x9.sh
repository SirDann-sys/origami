#!/bin/bash
# Episódio completo 16:9 (YouTube): renderiza cada parte na horizontal, segura o último quadro por 0,4 s
# (o mesmo respiro da emenda do áudio) e põe por baixo o áudio master do episódio (−16 LUFS).
# Uso: episodio_16x9.sh PASTA_OBRA EP NPARTES AUDIO_EPISODIO SAIDA ["RÓTULO FIXO"]
#   Rótulo fixo (ex.: "EPISÓDIO 1 · ARQUIVO") no lugar de "PARTE N/8"; marca d'água em tudo; cartão final só no fim.
P="$1"; EP="$2"; N="$3"; AUD="$4"; OUT="$5"; ROT="$6"
# tudo relativo à pasta do app
AQUI="$(cd "$(dirname "$0")" && pwd)"; RAIZ="$(cd "$AQUI/../.." && pwd)"
MARCA="${MARCA:-$(cygpath -w "$RAIZ/recursos/marca/padrao/marca.json")}"
# vindos da obra/marca (o motor do Origami preenche)
DESTAQUE="${DESTAQUE:-255,196,92}"
ARTISTA="${ARTISTA:-Origami}"; COMENTARIO="${COMENTARIO:-}"
DIREITOS="${DIREITOS:-}"
FF="$RAIZ/ffmpeg/ffmpeg.exe"
cd "$AQUI"
TMP=$(mktemp -d); LISTA="$TMP/lista.txt"
for k in $(seq 1 $N); do
  kk=$(printf %02d $k)
  "$RAIZ/ambientes/qwen/Scripts/python.exe" compor.py --formato horizontal --parte $k --plano "$P\\06_video\\plano_video_ep$EP.json" \
    --tempos "$P\\06_video\\tempos_ep$EP.json" --imagens "$P\\06_video\\imagens" --audio "$P\\05_audio\\ep$EP\\mix\\parte_${kk}_tiktok.wav" \
    --saida "$TMP/h_$kk.mp4" --rotulo "${ROT:-EPISÓDIO $((10#$EP)) · PARTE $k/$N}"     --marca "$MARCA" --destaque "$DESTAQUE" --ep $((10#$EP)) --cartao $([ $k -eq $N ] && echo fim || echo nenhum) 2>&1 | grep -E "^ok|Error|Trace"
  if [ $k -lt $N ]; then
    "$FF" -v error -y -i "$TMP/h_$kk.mp4" -vf "tpad=stop_mode=clone:stop_duration=0.4" -an -c:v h264_nvenc -preset p6 -cq 19 "$TMP/g_$kk.mp4"
  else
    "$FF" -v error -y -i "$TMP/h_$kk.mp4" -an -c:v copy "$TMP/g_$kk.mp4"
  fi
  echo "file '$(cygpath -w "$TMP/g_$kk.mp4")'" >> "$LISTA"
done
"$FF" -v error -y -f concat -safe 0 -i "$(cygpath -w "$LISTA")" -i "$AUD" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest   -metadata title="${ROT:-Episódio $EP}" -metadata artist="$ARTISTA" -metadata comment="$COMENTARIO"   -metadata copyright="$DIREITOS" "$OUT"
echo "ok $OUT"
