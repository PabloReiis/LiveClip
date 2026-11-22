"""Reparo seguro do CSS do editor visual LiveClipAI V2.

Corrige apenas o bloco CSS que foi inserido como texto fora de uma tag <style>
no arquivo web/index.html. Preserva o restante da interface, dados, configs
Whisper e motor de processamento. Usa --check para inspecionar.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile

CSS_START = b"/* LiveClip AI framing studio: original frame, draggable selections, 9:16 preview */"
CSS_END = b"<!-- LIVECLIP_V2_POLISH_CSS_END -->"
OPEN = b'<style id="liveclip-framing-editor-css">\n'
CLOSE = b'</style>\n'


def run(root: Path, check: bool) -> int:
    page = root / "web" / "index.html"
    if not page.is_file():
        print(f"ERRO: arquivo nao encontrado: {page}")
        return 2
    data = page.read_bytes()
    if data.count(CSS_START) != 1 or data.count(CSS_END) != 1:
        print("NAO ALTERADO: nao encontrei os marcadores exatos do editor visual.")
        print("Envie o arquivo web/index.html para uma correção compativel.")
        return 2
    a = data.index(CSS_START)
    b = data.index(CSS_END, a)
    block = data[a:b]
    preceding = data[:a].rstrip().lower()
    if preceding.endswith(b'<style id="liveclip-framing-editor-css">') or block.rstrip().lower().endswith(b'</style>'):
        print("OK: o CSS do editor ja esta dentro de <style>. Nenhuma alteracao.")
        return 0
    if b"</style" in block.lower() or b"<script" in block.lower():
        print("NAO ALTERADO: o trecho encontrado possui marcacao inesperada.")
        return 2
    # Critério específico para o bug: o CSS estava depois do fechamento
    # do style anterior e imediatamente antes do marcador de acabamento.
    if not preceding.endswith(b'</style>'):
        print("NAO ALTERADO: a estrutura do HTML nao corresponde ao erro conhecido.")
        return 2
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    open_tag = OPEN.replace(b"\n", newline)
    close_tag = CLOSE.replace(b"\n", newline)
    fixed = data[:a] + open_tag + data[a:b].rstrip() + newline + close_tag + data[b:]
    if check:
        print("CHECAGEM OK: CSS fora de <style> identificado. Nenhum arquivo alterado.")
        return 0
    backup_dir = root / 'liveclip_v2_backups' / ('editor_css_' + datetime.now().strftime('%Y%m%d_%H%M%S')) / 'web'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / 'index.html'
    shutil.copy2(page, backup)
    fd, tmp = tempfile.mkstemp(prefix='._liveclip_css_', dir=page.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(fixed)
        os.replace(tmp, page)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print('CORRECAO CONCLUIDA: CSS do editor colocado dentro de <style>.')
    print('Arquivo alterado: web/index.html')
    print('Backup anterior:', backup)
    print('Reinicie o servidor e aperte Ctrl+F5 no navegador.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=r'D:\LiveClipAI_V2')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(Path(args.root), args.check))
