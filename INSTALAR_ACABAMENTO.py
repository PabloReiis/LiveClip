"""LiveClip AI V2: acabamento visual sobre a SPA PeakCut existente.

Nao modifica studio/, API, bancos, configuracoes, motor, clips ou videos.
Compativel com os arquivos web/index.html da V2 enviados em 21/11/2026.

Uso:
  python INSTALAR_ACABAMENTO.py --root D:\\LiveClipAI_V2
  python INSTALAR_ACABAMENTO.py --root D:\\LiveClipAI_V2 --check
  python INSTALAR_ACABAMENTO.py --root D:\\LiveClipAI_V2 --restore
"""
from __future__ import annotations
import argparse
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import sys

START_CSS='<!-- LIVECLIP_V2_POLISH_CSS_BEGIN -->'
END_CSS='<!-- LIVECLIP_V2_POLISH_CSS_END -->'
START_JS='<!-- LIVECLIP_V2_POLISH_JS_BEGIN -->'
END_JS='<!-- LIVECLIP_V2_POLISH_JS_END -->'
JS_FILE='liveclip-polish-v2.js'

class IDs(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=set()
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if d.get('id'):self.ids.add(d['id'])

def required_html(root:Path)->tuple[Path,str]:
    index = root/'web'/'index.html'
    server = root/'studio'/'server.py'
    if not index.is_file() or not server.is_file():
        raise RuntimeError('Root invalido: esperado web/index.html e studio/server.py')
    source=index.read_bytes().decode('utf-8')
    ids=IDs();ids.feed(source)
    needed={'app','nav','view','actions','heroSlot','title'}
    if not needed.issubset(ids.ids):
        raise RuntimeError('HTML da V2 incompativel; IDs ausentes: '+','.join(sorted(needed-ids.ids)))
    if source.count('</head>')!=1 or source.count('</body>')!=1:
        raise RuntimeError('HTML inesperado; nada sera alterado')
    return index,source

def install(root:Path,source_dir:Path,check:bool=False):
    index,original = required_html(root)
    for marker in (START_CSS,END_CSS,START_JS,END_JS):
        if original.count(marker):
            if all(m in original for m in (START_CSS,END_CSS,START_JS,END_JS)):
                print('Acabamento LiveClip AI V2 ja instalado. Nenhuma mudanca.');return
            raise RuntimeError('Instalacao parcial detectada; nada alterado')
    # This installer is for the *branded* V2; do not mutate a separate vanilla clone.
    if '<!-- LIVECLIP_V2_THEME_BEGIN -->' not in original or '<!-- LIVECLIP_V2_BRAND_BEGIN -->' not in original:
        raise RuntimeError('Instale primeiro a identidade LiveClip V2 original; nao e a SPA esperada')
    css=(source_dir/'liveclip-polish.css').read_text(encoding='utf-8')
    js=(source_dir/JS_FILE).read_text(encoding='utf-8')
    if not css.strip() or not js.strip():
        raise RuntimeError('Pacote incompleto')
    js_target=root/'web'/JS_FILE
    if js_target.exists():
        raise RuntimeError('web/'+JS_FILE+' ja existe: protegido contra sobrescrita')
    # Files served by /assets must have extension .js; CSS is embedded in the HTML.
    css_part=f'{START_CSS}\n<style id="liveclip-v2-polish">\n{css}\n</style>\n{END_CSS}\n'
    js_part=f'{START_JS}\n<script src="/assets/{JS_FILE}?v=2"></script>\n{END_JS}\n'
    newline='\r\n' if '\r\n' in original else '\n'
    css_part=css_part.replace('\n',newline)
    js_part=js_part.replace('\n',newline)
    new=original.replace('</head>',css_part+'</head>',1).replace('</body>',js_part+'</body>',1)
    p=IDs();p.feed(new)
    if not {'app','nav','view','actions','heroSlot','title'}.issubset(p.ids):
        raise RuntimeError('Validacao de estrutura falhou')
    for marker in (START_CSS,END_CSS,START_JS,END_JS):
        if new.count(marker)!=1:
            raise RuntimeError('Marcadores incorretos')
    if check:
        print('VALIDADO: sera alterado somente web/index.html e adicionado web/'+JS_FILE)
        print('Tamanho do CSS:',len(css),'Tamanho JS:',len(js));return
    backup_dir=root/'liveclip_v2_backups'
    backup_dir.mkdir(parents=True,exist_ok=True)
    timestamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup=backup_dir/f'index_before_polish_{timestamp}.html'
    backup.write_bytes(original.encode('utf-8'))
    try:
        js_target.write_text(js,encoding='utf-8')
        temp=index.with_suffix('.html.livecliptmp')
        temp.write_bytes(new.encode('utf-8'))
        temp.replace(index)
    except BaseException:
        index.write_bytes(original.encode('utf-8'))
        js_target.unlink(missing_ok=True)
        raise
    print('OK: acabamento visual instalado.')
    print('Backup:',backup)
    print('Motor PeakCut, studio/, dados, videos e gravacoes preservados.')
    print('Reinicie o servidor e abra http://127.0.0.1:8767/app com Ctrl+F5.')

def remove_part(html:str,start:str,end:str)->str:
    if html.count(start)!=1 or html.count(end)!=1:
        raise RuntimeError('Marcadores de acabamento ausentes/incompletos; nao alterei nada')
    a=html.index(start);b=html.index(end)+len(end)
    if html.startswith('\r\n',b):b+=2
    elif html.startswith('\n',b):b+=1
    return html[:a]+html[b:]

def restore(root:Path):
    index,html=required_html(root)
    clean=remove_part(html,START_CSS,END_CSS)
    clean=remove_part(clean,START_JS,END_JS)
    js_path=root/'web'/JS_FILE
    backup_dir=root/'liveclip_v2_backups';backup_dir.mkdir(parents=True,exist_ok=True)
    saved=backup_dir/f'index_before_polish_restore_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.html'
    saved.write_bytes(html.encode('utf-8'))
    index.write_bytes(clean.encode('utf-8'))
    js_path.unlink(missing_ok=True)
    print('OK: acabamento removido, tema anterior preservado.')
    print('Backup da versao anterior a restauracao:',saved)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',default='D:/LiveClipAI_V2')
    p.add_argument('--check',action='store_true',help='Simula e valida, sem alterar nada')
    p.add_argument('--restore',action='store_true',help='Remove somente este acabamento')
    args=p.parse_args()
    root=Path(args.root).expanduser().resolve()
    if args.restore and args.check: p.error('--restore e --check nao podem ser usados juntos')
    try:
        if args.restore:restore(root)
        else:install(root,Path(__file__).resolve().parent,check=args.check)
    except Exception as exc:
        print('ERRO:',exc,file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
