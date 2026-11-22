#!/usr/bin/env python3
"""Instala suporte PT-BR na cópia específica do LiveClip AI V2 / PeakCut.

Altera somente os arquivos enumerados no manifest. Nunca apaga data/, nem .env.
Permite restaurar o backup explícito criado pela instalação.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write_atomic(path, content):
    tmp = path.with_name(path.name + '.liveclip-new')
    try:
        tmp.write_bytes(content)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def install(root, check=False):
    if not (root/'studio'/'server.py').is_file() or not (root/'web'/'index.html').is_file():
        raise RuntimeError('Pasta inválida: não encontrei studio/server.py e web/index.html. Escolha a raiz da V2.')
    operations=[]
    for rel, h in MANIFEST.items():
        path=root/rel
        content=path.read_bytes() if path.is_file() else None
        installed=content is not None and digest(content)==h['new_sha256']
        if installed:
            print('JÁ INSTALADO:',rel)
            continue
        expected=h['base_sha256']
        if expected is None and content is not None:
            raise RuntimeError(f'Arquivo já existe com conteúdo diferente: {path}. Nada foi alterado.')
        if expected is not None and (content is None or digest(content)!=expected):
            raise RuntimeError(f'O arquivo {rel} foi alterado depois do ZIP enviado. '
                               'Nada foi modificado. Envie a versão atual para adaptar sem sobrescrever suas mudanças.')
        source=HERE/'payload'/rel
        data=source.read_bytes()
        if digest(data)!=h['new_sha256']:
            raise RuntimeError(f'O pacote está corrompido ({rel}). Nada foi alterado.')
        operations.append((rel,path,content,data))
    if not operations:
        print('INSTALADO: todos os arquivos já estão atualizados.')
        return
    print('Arquivos que serão alterados:',len(operations))
    for rel,*_ in operations: print(' ',rel)
    if check:
        print('CHECAGEM OK: nenhum arquivo foi alterado.')
        return
    backup=root/'liveclip_v2_backups'/('ptbr_'+time.strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    info={'created':[], 'changed':[], 'root':str(root)}
    for rel,path,old,data in operations:
        if old is None:
            info['created'].append(rel)
        else:
            copy=backup/'original'/rel
            copy.parent.mkdir(parents=True,exist_ok=True)
            copy.write_bytes(old)
            info['changed'].append(rel)
    (backup/'restauracao.json').write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding='utf-8')
    applied=[]
    try:
        for rel,path,old,data in operations:
            path.parent.mkdir(parents=True,exist_ok=True)
            write_atomic(path,data)
            applied.append((path,old))
    except Exception:
        for path,old in reversed(applied):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                write_atomic(path,old)
        raise
    print('\nINSTALAÇÃO PT-BR CONCLUÍDA!')
    print('BACKUP:',backup)
    print('Não foram modificados: dados, .env, vídeos, banco e modelos já instalados.')
    print('Próximo passo: instalar requirements-ptbr.txt no .venv e reiniciar o servidor.')

def restore(root, backup):
    meta_file=backup/'restauracao.json'
    if not meta_file.is_file():
        raise RuntimeError('Backup inválido: faltou restauracao.json.')
    info=json.loads(meta_file.read_text(encoding='utf-8'))
    if Path(info['root']).resolve()!=root.resolve():
        raise RuntimeError('Este backup não foi criado para essa pasta.')
    for rel in info['changed']:
        source=backup/'original'/rel
        if not source.is_file():
            raise RuntimeError('Backup incompleto. Nenhum arquivo foi alterado.')
    for rel in info['changed']:
        write_atomic(root/rel,(backup/'original'/rel).read_bytes())
        print('RESTAURADO:',rel)
    for rel in info['created']:
        dest=root/rel
        if dest.is_file() and digest(dest.read_bytes())==MANIFEST[rel]['new_sha256']:
            dest.unlink()
            print('ARQUIVO ADICIONADO REMOVIDO:',rel)
    print('RESTaURAÇÃO CONCLUÍDA. Reinicie o servidor.')

def main():
    parser=argparse.ArgumentParser(description='Instalador PT-BR Whisper para LiveClip AI V2.')
    parser.add_argument('--root',default=r'D:\LiveClipAI_V2')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--restore',default=None,help='Caminho da pasta do backup criado por este instalador')
    a=parser.parse_args()
    try:
        root=Path(a.root).resolve()
        if a.restore:
            restore(root,Path(a.restore).resolve())
        else:
            install(root,a.check)
    except Exception as exc:
        print('\nERRO:',exc,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
