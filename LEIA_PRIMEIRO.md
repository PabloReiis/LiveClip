# LiveClip AI V2 — Português (Brasil) usando Whisper Small

## O que muda
- Adiciona **Português (Brasil)** em Configurações > Speech models.
- Usa **faster-whisper Small multilíngue** no PC, com timestamps por palavra para áudio de 16 kHz.
- A seleção de momentos continua sendo feita pelo **motor PeakCut + Gemini** já configurado.
- Mantém legendas em PT-BR, sem a tradução automática para inglês. Solicita títulos e ganchos em PT-BR quando a transcrição é portuguesa.
- Mantém o suporte existente a inglês e árabe.
- Modifica somente arquivos de código explicitados no manifest, sem acessar ou copiar .env, contas, banco ou vídeos.

## Instalação — PowerShell
**Primeiro finalize as gravações e feche o servidor PeakCut V2 (Ctrl+C).**
Extraia este ZIP para uma pasta separada, por exemplo `D:\LiveClipAI_V2_PTBR`.

```powershell
cd D:\LiveClipAI_V2
$instalador = Get-ChildItem 'D:\LiveClipAI_V2_PTBR' -Filter INSTALAR_PTBR.py -Recurse -File | Select-Object -First 1
& '.\.venv\Scripts\python.exe' $instalador.FullName --root 'D:\LiveClipAI_V2' --check
& '.\.venv\Scripts\python.exe' $instalador.FullName --root 'D:\LiveClipAI_V2'
& '.\.venv\Scripts\python.exe' -m pip install -r '.\requirements-ptbr.txt'
& '.\.venv\Scripts\python.exe' -m pip check
```

Depois inicie o servidor:

```powershell
$env:PEAKCUT_PORT = '8767'
$env:PEAKCUT_DATA = 'D:\LiveClipAI_V2\data'
$env:PEAKCUT_FETCH_MODEL = '0'
& '.\.venv\Scripts\python.exe' -m studio.server
```

Abra `http://127.0.0.1:8767/app` > Configurações > **Speech models** > **Português (Brasil)** > **Baixar**.
Aproximadamente 500 MB de download de pesos, sujeito a variações. O progresso desse modelo não é granular (pode permanecer em 5% enquanto baixa). Aguarde o estado **Ready/Pronto**.

Em **Adicionar canal** escolha **Português (Brasil)** como idioma do criador, ou ao adicionar um vídeo, em **Opções > Spoken language**. O PeakCut não adivinha automaticamente que o streamer fala português. A chave Gemini já cadastrada continua como está.

## Teste rápido de reconhecimento
Com modelo instalado e terminal na raiz da V2:

```powershell
& '.\.venv\Scripts\python.exe' -c "from studio import fetch_model,brain; print('PT-BR:',fetch_model.status('pt')); print('Legendas em PT-BR:',not brain.needs_translation('pt'))"
```

Saída esperada `PT-BR: ready` e `Legendas em PT-BR: True`. Isso verifica o modelo presente e a regra de legendas, **não** uma transcrição real. Para validar fala e cortes, faça um teste com vídeo seu ou autorizado e confirme os timestamps, texto, qualidade e velocidade de processamento.

## Limitações
- A transcrição via Whisper Small pode atrasar a análise ao vivo no CPU; por segurança a configuração inicial usa CPU/int8, sem exigir drivers CUDA. A RTX 4060 pode exigir outras bibliotecas para usar CUDA com faster-whisper, não habilitado automaticamente.
- O modelo é baixado diretamente pelo faster-whisper da Hugging Face na primeira instalação; é necessária conexão. Não acompanha o ZIP.
- A configuração Gemini deve permanecer válida. A qualidade de identificação dos cortes ainda depende do prompt, áudio e IA, não apenas da existência de transcrição.
- Este pacote não altera o layout dos vídeos (webcam + gameplay) nem adiciona nova moldura/editor.
- O `asr_worker` remoto sherpa antigo não processa português; português usa o modelo local por padrão.
- Se seu projeto for modificado depois da coleta do ZIP original, o instalador aborta para não sobrescrever alterações.

## Desfazer
O instalador informa o local do backup, por exemplo `D:\LiveClipAI_V2\liveclip_v2_backups\ptbr_20261121_...`.
Com o servidor parado:

```powershell
& '.\.venv\Scripts\python.exe' $instalador.FullName --root 'D:\LiveClipAI_V2' --restore 'D:\LiveClipAI_V2\liveclip_v2_backups\ptbr_NOME_DO_BACKUP'
```

Não há necessidade de apagar o modelo de português em `data` para restaurar o código. O backup preserva os arquivos originais.
