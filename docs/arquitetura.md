# Arquitetura

## Processos

| Processo | Papel |
|---|---|
| `app/main.js` (Electron) | Abre a janela, sobe o motor se ele não estiver no ar e religa o motor quando ele cai. Se houver mais de 3 quedas em 10 minutos, para e mostra o registro. |
| `motor/worker.py` | Servidor HTTP local (API + interface) e **worker**: pega um job por vez da fila SQLite, roda a etapa e registra os artefatos. É o único processo que usa a GPU. |
| `motor/piloto.py` | Com a fila parada, decide o próximo passo de cada episódio com o piloto ligado e o põe na fila. |
| Serviços locais | Servidor de voz e ComfyUI. O motor liga cada um quando um job precisa e desliga na troca de recurso de GPU. |
| `claude -p` | Tarefas de texto e a triagem visual. Cada chamada é isolada e roda numa pasta de trabalho fora do projeto. |

## Do texto ao episódio

### 1. Obra nova (`motor/obra_nova.py`)
O arquivo bruto (txt, md, docx, pdf ou log de RPG) vira `00_fonte/texto_limpo.txt`. A IA lê bloco a bloco
(`ler_bloco`), divide a obra em episódios (`estrutura`), escreve o guia de cada episódio (`guia_ep`) e monta a
bíblia, as inconsistências a decidir, o guia de arte e a pronúncia (`obra_biblia`).

### 2. Texto (`motor/texto.py`)
- O **nível de IA** de cada episódio define quanto a IA pode mexer no texto: `preservar` (o texto do autor é o mestre, sem passar pela IA), `revisar`, `expandir`, `recriar` ou `continuar`.
- `mestre` escreve o texto-mestre. Depois, `alarme` procura erros de continuidade contra o mapa da obra, e `corrigir` aplica a menor mudança possível em cada alerta crítico.
- **Portão:** o autor aprova o texto-mestre.

### 3. Roteiro (`motor/roteiro.py`)
O mestre aprovado é dividido em partes curtas, com voz, pausa, estilo, cenário, humor e final musical para cada fala.
Conferências sem IA: duração estimada por parte, repetições e vozes ou cenários válidos.
Uma voz nova vira decisão na Mesa.

### 4. Produção (`motor/etapas.py`)

```
sincronizar → voz → montar → cue → stems → mix → episodio
                                   └→ tempos → video (9:16) → video16x9
                                                capas · wattpad · entregar
```

Cada etapa declara `recurso` (cpu, gpu:voz, gpu:whisper, gpu:imagem, nvenc), `escopo` (episódio ou parte),
`entradas`, `saidas` e `rodar`. A assinatura (sha1) das entradas decide a **situação** da etapa:

| Situação | Quando | O que acontece |
|---|---|---|
| em dia | saídas existem e nada mudou | a etapa é pulada |
| refazer | falta saída ou mudou uma entrada | entra na fila (só a parte afetada) |
| código novo | só o script mudou | a Mesa avisa; só roda se o autor aplicar |

`DEPENDE` liga cada etapa às anteriores: quando uma falha, só caem as etapas que dependem dela.

**Portões:** escolher e aprovar as vozes (Elenco) e ouvir e aprovar o áudio do episódio. Legenda, vídeos e entrega só
entram na fila depois da aprovação do áudio.

### 5. Arte (`motor/arte.py`, `motor/triagem.py`, `motor/imagens_video.py`)
`cenas` propõe uma cena por capa, a miniatura e o topo do capítulo. Cada pedido usa marcadores `{personagem@contexto}`,
que viram a descrição fixa da ficha da personagem e as imagens de referência dela. Cada imagem gerada passa pela
conferência sem IA (`ferramentas/video/conferir_imagem.py`) e depois pela triagem visual (`triagem`).
A pré-escolhida vale sozinha depois do prazo. Uma imagem escolhida à mão nunca é trocada automaticamente.

### 6. Publicação (`motor/kit.py`, `motor/publicacao.py`, `motor/postagem.py`)
`kit` escreve título, descrição, capítulos, legendas e comentário fixado com frases reais do texto, sem spoiler.
As peças finais ficam em `PUBLICAR/EpNN` como hardlinks (sem duplicar no disco). O calendário de postagem
sugere as datas, e o autor posta e marca o que foi feito. O app nunca posta sozinho.

## O trabalhador de texto (`motor/trabalhador.py`)

- Uma tarefa = `trabalhador/<tarefa>.md` (system prompt) + `<tarefa>.schema.json` (saída obrigatória).
- A entrada é um JSON mínimo, montado pela etapa, com só o que a tarefa precisa.
- O consumo (tokens, custo, segundos) vai para `<obra>/custo.jsonl` e aparece na tela Fila e custo.
- Ao atingir o limite de uso, a tarefa lança `LimiteClaude` com o horário de volta. O worker adia só os jobs de texto e segue com o resto da fila.

## Pasta de uma obra

```
00_fonte/          texto original e texto limpo
01_biblia/         bíblia, guia por episódio, decisões, guia de arte, pronúncia
02_capitulos/      texto-mestre de cada episódio, alertas e versões anteriores
03_personagens/    referências visuais
04_roteiro_audio/  roteiro e relatório de conferência
05_audio/          falas, partes, trilha e mixagem
06_video/          imagens de cenário e retrato, tempos, legendas e vídeos
07_publicacao/     arte, capas, kit e capítulo para leitura
PUBLICAR/EpNN/     peças finais, prontas para postar
projeto.json       configuração da obra e estado de cada episódio
```

## Modo demonstração

`ORIGAMI_DEMO=1` muda o comportamento do motor assim:
- `PROJETOS` passa a apontar para `exemplos/` e o banco vai para `dados/demo/`;
- não sobe worker nem piloto, e qualquer POST responde 403 com a mensagem da demonstração;
- `semear_demo()` registra como "em dia" toda etapa cujas saídas já existem, porque o banco começa vazio;
- as respostas trocam o caminho da pasta do app por caminhos relativos;
- a Mesa marca como "fora da demonstração" as etapas cujos arquivos pesados não vão no repositório (stems, episódio completo, 16:9).

Na interface, `GET /api/ambiente` liga `interface/demo.js`, que mostra a faixa no topo e o tour guiado
(`#tour=N` abre direto no passo N).

O atalho `abrir_demo.bat` / `abrir_demo.sh` prepara o `.venv` e sobe com `ORIGAMI_PORTA=0` (uma porta livre) e
`ORIGAMI_ABRIR=1` (abre o navegador).

A versão online é a mesma interface, servida estaticamente. Veja "Como a demonstração online funciona" no README.

## Testes

`testes/` cobre o piloto (portões, erro que vira pendência, freio para ação repetida, prazo da pré-escolhida),
o worker (queda, serviço que não sobe, limite da IA, retomada), os ajustes e o inventário de arquivos, e a conferência de voz (números por extenso, WER).
Os testes usam banco e obras temporários.
