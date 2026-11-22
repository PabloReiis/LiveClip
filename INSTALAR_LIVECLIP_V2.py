"""Instalador conservador do visual LiveClip AI sobre a SPA do PeakCut.

Uso (Windows):
  cd D:\\LiveClipAI_V2
  & '.\\.venv\\Scripts\\python.exe' 'D:\\...\\INSTALAR_LIVECLIP_V2.py' --root 'D:\\LiveClipAI_V2'

Somente web/index.html e web/liveclip-v2.js são alterados. Nunca muda studio/, DB,
credenciais, captura, a fila, vídeos ou arquivos de configuração do PeakCut.
"""
from __future__ import annotations
import argparse
import datetime as dt
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys

CSS_BEGIN = "<!-- LIVECLIP_V2_THEME_BEGIN -->"
CSS_END = "<!-- LIVECLIP_V2_THEME_END -->"
JS_BEGIN = "<!-- LIVECLIP_V2_JS_BEGIN -->"
JS_END = "<!-- LIVECLIP_V2_JS_END -->"
BRAND_BEGIN = "<!-- LIVECLIP_V2_BRAND_BEGIN -->"
BRAND_END = "<!-- LIVECLIP_V2_BRAND_END -->"

BRAND_HTML = '''<!-- LIVECLIP_V2_BRAND_BEGIN -->
<div class="lc-brand" role="img" aria-label="LiveClip AI">
  <span class="lc-brand-symbol" aria-hidden="true">
    <svg viewBox="0 0 32 32"><rect x="4" y="5" width="24" height="22" rx="7"/><path d="m13 11 9 5-9 5V11Z" fill="currentColor" stroke="none"/><path d="M10 3h12" stroke-linecap="round"/></svg>
  </span>
  <span class="lc-brand-copy"><strong>LiveClip <em>AI</em></strong><small>STUDIO · MOTOR PEAKCUT</small></span>
</div>
<!-- LIVECLIP_V2_BRAND_END -->'''

ORIGINAL_LOGOS = ('<img class="logo" src="/brand/logo-light.svg" alt="PeakCut">'
                  '<img class="mark" src="/brand/favicon.svg" alt="PeakCut">')

class HTMLCheck(HTMLParser):
    def __init__(self):
        super().__init__(); self.identifiers=set()
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if data.get('id'): self.identifiers.add(data['id'])


def validate(root: Path):
    index=root/'web'/'index.html'
    server=root/'studio'/'server.py'
    if not index.is_file() or not server.is_file():
        raise ValueError('Pasta invalida: nao encontrei web/index.html e studio/server.py do PeakCut.')
    html=index.read_text(encoding='utf-8-sig')
    parser=HTMLCheck();parser.feed(html)
    required={'app','nav','view','actions','heroSlot','title'}
    if not required.issubset(parser.identifiers):
        raise ValueError('Versao do PeakCut diferente da esperada; nao alterei nada. Faltam IDs: '
                         + ', '.join(sorted(required-parser.identifiers)))
    if '</head>' not in html or '</body>' not in html:
        raise ValueError('HTML do PeakCut incompleto; nada alterado.')
    return index,html


def install(root:Path,source:Path):
    index,html=validate(root)
    if CSS_BEGIN in html or JS_BEGIN in html or BRAND_BEGIN in html:
        print('Ja existe uma integracao LiveClip V2 neste HTML. Nada alterado.')
        print('Para reinstalar: execute este instalador com --restore, depois instale novamente.')
        return
    if html.count(ORIGINAL_LOGOS)!=1:
        raise ValueError('Nao achei a marca original do PeakCut onde esperava. Nada alterado.')
    theme=(source/'liveclip_theme.css').read_text(encoding='utf-8')
    script=source/'liveclip-v2.js'
    if not script.is_file() or not theme.strip():
        raise ValueError('Os arquivos do pacote estao incompletos. Nada alterado.')
    if (root/'web'/'liveclip-v2.js').exists():
        raise ValueError('web/liveclip-v2.js ja existe; para nao sobrescrever, nada foi alterado.')
    # Build the entire output before touching the user's copy.
    modified=html.replace(ORIGINAL_LOGOS,BRAND_HTML,1)
    modified=modified.replace('<title>PeakCut</title>','<title>LiveClip AI V2 · PeakCut</title>',1)
    modified=modified.replace('</head>', f'{CSS_BEGIN}\n<style id="liveclip-v2-theme">\n{theme}\n</style>\n{CSS_END}\n</head>',1)
    modified=modified.replace('</body>', f'{JS_BEGIN}\n<script src="/assets/liveclip-v2.js"></script>\n{JS_END}\n</body>',1)
    required_markers=[CSS_BEGIN,CSS_END,JS_BEGIN,JS_END,BRAND_BEGIN,BRAND_END]
    if any(modified.count(m)!=1 for m in required_markers):
        raise ValueError('Falha na validacao do HTML gerado. Nada alterado.')
    again=HTMLCheck();again.feed(modified)
    if not {'app','nav','view','actions','heroSlot','title'}.issubset(again.identifiers):
        raise ValueError('Estrutura do aplicativo seria alterada. Cancelado.')
    backup_root=root/'liveclip_v2_backups'
    backup_root.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    original=backup_root/f'index_before_liveclip_{stamp}.html'
    original.write_text(html,encoding='utf-8')
    try:
        shutil.copy2(script,root/'web'/'liveclip-v2.js')
        index.write_text(modified,encoding='utf-8')
        (backup_root/'LAST_BACKUP.txt').write_text(str(original.name),encoding='utf-8')
    except BaseException:
        index.write_text(html,encoding='utf-8')
        (root/'web'/'liveclip-v2.js').unlink(missing_ok=True)
        raise
    print('OK: identidade visual LiveClip AI aplicada ao painel PeakCut!')
    print('Backup do HTML:',original)
    print('Motor studio/ preservado; nenhum video ou banco de dados foi modificado.')
    print('Reinicie o PeakCut e abra http://127.0.0.1:8767/app (Ctrl+F5).')


def restore(root:Path):
    index,_=validate(root)
    backup_root=root/'liveclip_v2_backups'
    pointer=backup_root/'LAST_BACKUP.txt'
    if not pointer.exists():
        raise ValueError('Nenhum backup gerado por este instalador encontrado. Nada alterado.')
    filename=pointer.read_text(encoding='utf-8').strip()
    if Path(filename).name!=filename or not filename.startswith('index_before_liveclip_') or not filename.endswith('.html'):
        raise ValueError('Ponteiro de backup invalido; nada alterado.')
    original=backup_root/filename
    if not original.is_file():
        raise ValueError('Backup original nao existe; nada alterado.')
    backup=original.read_text(encoding='utf-8')
    index.write_text(backup,encoding='utf-8')
    (root/'web'/'liveclip-v2.js').unlink(missing_ok=True)
    pointer.unlink(missing_ok=True)
    print('Painel original do PeakCut restaurado:',index)
    print('studio/, banco e videos continuam intactos.')


def main():
    ap=argparse.ArgumentParser(description='Aplica/restaura identidade LiveClip AI no PeakCut existente.')
    ap.add_argument('--root',default='D:/LiveClipAI_V2',help='Pasta da copia PeakCut V2')
    ap.add_argument('--restore',action='store_true',help='Restaura HTML original salvo pelo instalador')
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()
    try:
        if args.restore: restore(root)
        else: install(root,Path(__file__).resolve().parent)
    except Exception as e:
        print('ERRO:',e,file=sys.stderr);sys.exit(1)

if __name__=='__main__': main()
