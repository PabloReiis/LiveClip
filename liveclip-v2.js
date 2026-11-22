/* LiveClip AI visual adaptation for PeakCut SPA. No API replacements.
   Keep all original data-act attributes, view rendering, session/auth and POST flows. */
(() => {
  'use strict';
  if (!document.querySelector('#app .side') || !document.querySelector('#view')) return;
  const labels = Object.freeze({
    'Home': 'Visão geral',
    'All videos': 'Gravações e cortes',
    'Creators': 'CANAIS / CRIADORES',
    'New creator': 'Adicionar canal',
    'Settings': 'Configurações',
    'AI usage': 'Uso de IA',
    'Owner': 'ADMINISTRAÇÃO',
    'Admin dashboard': 'Painel administrativo',
    'Live': 'Ao vivo',
    'Rec': 'Gravando',
    'Not set up': 'Não configurada',
    'Ready': 'Pronta',
    'New video': 'Novo vídeo',
    'Upload': 'Enviar vídeo',
    'Go live': 'Iniciar live',
    'Start recording': 'Iniciar gravação',
    'Stop recording': 'Parar gravação',
    'Start clipping': 'Iniciar cortes',
    'Stop clipping': 'Parar cortes',
    'AI settings': 'Configurações de IA',
    'AI': 'IA',
    'YouTube': 'YouTube',
    'TikTok': 'TikTok',
    'Instagram': 'Instagram',
    'Cancel': 'Cancelar',
    'Save': 'Salvar',
    'Close': 'Fechar',
    'Delete': 'Excluir',
    'Edit': 'Editar',
    'Overview': 'Visão geral',
    'Clips': 'Cortes',
    'Recordings': 'Gravações',
    'Setup': 'Configuração',
    'Activity': 'Atividade',
    'Connected apps': 'Contas conectadas',
    'Channels': 'Canais',
    'Videos': 'Vídeos',
    'Today': 'Hoje',
    'Good morning': 'Bom dia',
    'Good afternoon': 'Boa tarde',
    'Good evening': 'Boa noite',
  });
  const nodes = '#nav, #title, #subtitle, #actions, #utabs, #view, #heroSlot';
  let scheduled = false;
  function translate() {
    scheduled = false;
    for (const root of document.querySelectorAll(nodes)) {
      const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: node => {
          if (!node.parentElement || node.parentElement.closest('script,style,textarea,code,pre,[contenteditable="true"]')) return NodeFilter.FILTER_REJECT;
          const s = node.nodeValue.trim();
          return Object.prototype.hasOwnProperty.call(labels,s) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }
      });
      const found=[];
      while (walk.nextNode()) found.push(walk.currentNode);
      for (const n of found) {
        const content=n.nodeValue, trimmed=content.trim();
        n.nodeValue = content.replace(trimmed, labels[trimmed]);
      }
    }
  }
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(translate);
  }
  const app=document.querySelector('#app');
  const obs=new MutationObserver(schedule);
  obs.observe(app,{subtree:true,childList:true,characterData:true});
  document.addEventListener('DOMContentLoaded',schedule,{once:true});
  schedule();
})();
