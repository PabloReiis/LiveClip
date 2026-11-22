/* LiveClip AI V2: traduz SOMENTE textos da interface do PeakCut.
 * Nenhuma rota, data-act, onclick, estado ou requisicao HTTP e interceptada.
 * Reage aos redesenhos da SPA (MutationObserver).
 */
(() => {
  'use strict';
  const root = document.getElementById('app');
  if (!root || !document.getElementById('view')) return;
  document.documentElement.lang = 'pt-BR';
  const tr = Object.freeze({
    'Recording now':'Gravando agora','Clips today':'Cortes hoje',
    'Posted today':'Publicados hoje','Waiting to post':'Aguardando publicação',
    'Activity':'Atividade','Last 14 days':'Últimos 14 dias',
    'Clips made':'Cortes criados','Posted':'Publicados',
    'Views':'Visualizações','Est. earnings':'Receita estimada',
    'No clips in the last 14 days yet':'Nenhum corte nos últimos 14 dias',
    'AI not configured':'IA não configurada','AI not set up':'IA não configurada',
    'Not configured':'Não configurada','Not set up':'Não configurada',
    'Clips are picked by loudness until an AI key is added.':'Sem chave de IA, a seleção usa apenas volume do áudio.',
    'AI calls today':'Chamadas de IA hoje','Tokens today':'Tokens hoje',
    'Add AI key':'Configurar chave de IA','View usage':'Ver consumo',
    'Creators':'Criadores','Each creator\'s status and results':'Situação e resultados por canal',
    'Creator':'Criador','Status':'Estado','Auto-post':'Publicação automática',
    'Failed':'Falhou','Waiting':'Aguardando','Est. $':'Receita estimada',
    'Your day at a glance':'Seu dia em resumo',
    'Recordings':'Gravações','Clips':'Cortes','Home':'Visão geral',
    'All videos':'Gravações e cortes','New creator':'Adicionar canal',
    'New video':'Novo vídeo','Upload video':'Enviar vídeo',
    'No creator':'Sem canal','Options':'Opções','Make clips':'Criar cortes',
    'Upload':'Enviar','Cancel':'Cancelar','Save':'Salvar','Close':'Fechar',
    'Delete':'Excluir','Edit':'Editar','Download':'Baixar','Share':'Compartilhar',
    'Play':'Reproduzir','Stop':'Parar','Pause':'Pausar',
    'Go live':'Iniciar live','Record this stream':'Gravar esta live',
    'Stop recording':'Parar gravação','Start recording':'Iniciar gravação',
    'Record':'Gravar','Recording':'Gravando','Recorded':'Gravado',
    'Kept in buffer':'Preservado no buffer','Clips so far':'Cortes até agora',
    'AI calls':'Chamadas à IA','AI checks every':'Verificações de IA a cada',
    'Loudness, last minute':'Volume no último minuto',
    'Settings':'Configurações','Connected apps':'Contas conectadas',
    'AI settings':'Configurações de IA','AI usage':'Consumo de IA',
    'No clips yet':'Nenhum corte ainda','No videos yet':'Nenhum vídeo ainda',
    'Processing':'Processando','Pending':'Pendente','Completed':'Concluído',
    'Ready':'Pronto','Live':'Ao vivo','Today':'Hoje',
    'Overview':'Visão geral','Dashboard':'Painel',
    'Add channel':'Adicionar canal','Add creator':'Adicionar criador',
    'Start':'Iniciar','Finish':'Concluir','Continue':'Continuar',
    'Help':'Ajuda','Search':'Pesquisar','Apply':'Aplicar',
    'Video':'Vídeo','Videos':'Vídeos','Captions':'Legendas',
    'Trim':'Recortar','Crop':'Enquadrar','Style':'Estilo',
    'Preview':'Prévia','Publish':'Publicar','Post':'Publicar',
    'Retry':'Tentar novamente','Refresh':'Atualizar','Details':'Detalhes',
    'History':'Histórico','Add':'Adicionar','Remove':'Remover',
    'Connected':'Conectado','Disconnected':'Desconectado',
    'Your videos':'Seus vídeos','Recording ended':'Gravação encerrada',
    'Choose a creator':'Escolher canal','Choose creator':'Escolher canal',
    'Sign out':'Sair','Account':'Conta','Profile':'Perfil',
    'Notifications':'Notificações','Creator settings':'Configurações do canal',
    'Choose a layout':'Escolha um layout',
    'Good morning':'Bom dia','Good afternoon':'Boa tarde','Good evening':'Boa noite',
    'Follow me':'Siga-me', 'Star on GitHub':'GitHub do PeakCut',
  });
  const placeholders = Object.freeze({
    'Paste a YouTube, Twitch or Kick video link':'Cole o link de vídeo do YouTube, Twitch ou Kick',
    'Paste a YouTube, Twitch or Kick video link here':'Cole o link de vídeo do YouTube, Twitch ou Kick aqui',
    'Search':'Pesquisar',
  });
  const scope = '#nav,#title,#subtitle,#actions,#utabs,#view,#heroSlot,#acctpop,#bellpop';
  let pending = false;
  const exclude = 'script,style,textarea,code,pre,[contenteditable],.transcript,.subtitle-line,.caption-text';
  function translate() {
    pending = false;
    const roots = document.querySelectorAll(scope);
    for (const node of roots) {
      if (!node) continue;
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
        acceptNode(t) {
          if (!t.parentElement || t.parentElement.closest(exclude)) return NodeFilter.FILTER_REJECT;
          return Object.prototype.hasOwnProperty.call(tr,t.nodeValue.trim()) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }
      });
      const found=[];
      while (walker.nextNode()) found.push(walker.currentNode);
      for (const t of found) {
        const raw=t.nodeValue, trimmed=raw.trim();
        if (tr[trimmed] && raw !== tr[trimmed]) t.nodeValue = raw.replace(trimmed,tr[trimmed]);
      }
      for (const el of node.querySelectorAll('[placeholder],[title],[aria-label]')) {
        for (const attr of ['placeholder','title','aria-label']) {
          const old = el.getAttribute(attr);
          if (old && Object.prototype.hasOwnProperty.call(tr,old)) el.setAttribute(attr,tr[old]);
          if (attr==='placeholder' && old && Object.prototype.hasOwnProperty.call(placeholders,old)) el.setAttribute(attr,placeholders[old]);
        }
      }
    }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(translate);
  }
  const mo = new MutationObserver(schedule);
  mo.observe(root,{subtree:true,childList:true,characterData:true});
  document.addEventListener('DOMContentLoaded',schedule,{once:true});
  schedule();
})();
