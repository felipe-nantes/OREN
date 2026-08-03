(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const root = document.documentElement;
  const body = document.body;
  const revealSelector = [
    '.page-hero .eyebrow',
    '.page-hero .page-title',
    '.page-hero .page-lead',
    '.page-hero .status-row',
    '.analysis-workspace > .card',
    '.clinical-context',
    '.benchmark-grid > .card',
    '#progressCard',
    '#reportCard',
    '.section-report-title',
    '.metrics > .metric',
    '.split > .card',
    '.subtype-report',
  ].join(',');

  const reveal = element => {
    if (!element || element.classList.contains('is-revealed')) return;
    requestAnimationFrame(() => element.classList.add('is-revealed'));
  };

  let observer;
  const prepare = (scope = document) => {
    const nodes = [...scope.querySelectorAll(revealSelector)];
    nodes.forEach((element, index) => {
      // Elementos de resultado começam ocultos pelo fluxo atual. Prepará-los
      // apenas quando aparecem preserva a entrada animada sem tocar no estado.
      if (element.classList.contains('hidden')) return;
      if (element.dataset.orenReveal === 'true') return;
      element.dataset.orenReveal = 'true';
      element.style.setProperty('--oren-delay', `${Math.min(index % 5, 4) * 70}ms`);
      if (reduced.matches || element.getBoundingClientRect().top < window.innerHeight * 0.92) reveal(element);
      else observer?.observe(element);
    });
  };

  const updateScroll = () => {
    const max = Math.max(document.documentElement.scrollHeight - innerHeight, 1);
    root.style.setProperty('--oren-scroll', `${Math.min(scrollY / max, 1) * 100}%`);
    document.querySelector('.app-header')?.classList.toggle('is-compact', scrollY > 28);
  };

  const init = () => {
    body.classList.add('oren-ready');
    observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        reveal(entry.target);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -5% 0px' });
    prepare();
    updateScroll();
    addEventListener('scroll', updateScroll, { passive: true });
    addEventListener('resize', updateScroll, { passive: true });

    new MutationObserver(mutations => {
      for (const mutation of mutations) {
        if (mutation.type === 'attributes' && mutation.target instanceof HTMLElement && !mutation.target.classList.contains('hidden')) {
          prepare(mutation.target.parentElement || document);
          reveal(mutation.target);
        }
        mutation.addedNodes.forEach(node => {
          if (node instanceof HTMLElement) {
            prepare(node);
            if (node.matches(revealSelector)) reveal(node);
          }
        });
      }
    }).observe(body, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
