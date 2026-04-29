console.log("[vehicle-offers] JS carregado");

(function () {
  'use strict';

  var TRUSTED_ORIGINS = ['https://chatgpt.com', 'https://chat.openai.com'];

  function log() {
    var args = Array.prototype.slice.call(arguments);
    args.unshift('[vehicle-offers]');
    console.log.apply(console, args);
  }

  function getToolOutput() {
    if (window.openai && window.openai.toolOutput)        return window.openai.toolOutput;
    if (window.openai && window.openai.toolResponse)      return window.openai.toolResponse;
    if (window.openai && window.openai.structuredContent) return { structuredContent: window.openai.structuredContent };
    return null;
  }

  function extractStructuredContent(payload) {
    if (!payload) return null;
    // compra
    if (payload.type === 'vehicle_cards') return payload;
    // venda
    if (payload.mode === 'sell') return payload;
    // aninhado em structuredContent
    var sc = payload.structuredContent;
    if (sc) {
      if (sc.type === 'vehicle_cards' || sc.mode === 'sell') return sc;
    }
    // aninhado em params.structuredContent (postMessage)
    var psc = payload.params && payload.params.structuredContent;
    if (psc && (psc.type === 'vehicle_cards' || psc.mode === 'sell')) return psc;
    return null;
  }

  /* ── Formatters ── */

  function fmtPrice(v) {
    if (v == null) return 'Consultar';
    var n = parseFloat(String(v).replace(/[^\d,.]/g, '').replace(',', '.'));
    if (isNaN(n) || n <= 0) return 'Consultar';
    var parts = n.toFixed(2).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'R$ ' + parts[0] + ',' + parts[1];
  }

  function fmtKm(v) {
    if (v == null || v === '') return '';
    var n = parseInt(String(v).replace(/\D/g, ''), 10);
    if (isNaN(n)) return '';
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' km';
  }

  function maskTel(v) {
    var d = v.replace(/\D/g, '').slice(0, 11);
    if (d.length <= 2)  return '(' + d;
    if (d.length <= 6)  return '(' + d.slice(0,2) + ') ' + d.slice(2);
    if (d.length <= 10) return '(' + d.slice(0,2) + ') ' + d.slice(2,6) + '-' + d.slice(6);
    return '(' + d.slice(0,2) + ') ' + d.slice(2,7) + '-' + d.slice(7);
  }

  function safeUrl(url) {
    if (!url || typeof url !== 'string') return null;
    try {
      var u = new URL(url);
      return u.protocol === 'https:' ? url : null;
    } catch (_) { return null; }
  }

  /* ── DOM helpers ── */

  function el(tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function txt(str) {
    return document.createTextNode(str == null ? '' : String(str));
  }

  /* ── Bridge: chama tool MCP via host ── */

  function callTool(name, args) {
    if (window.openai && typeof window.openai.callTool === 'function') {
      return Promise.resolve(window.openai.callTool(name, args));
    }
    if (window.mcpBridge && typeof window.mcpBridge.callTool === 'function') {
      return Promise.resolve(window.mcpBridge.callTool(name, args));
    }
    return Promise.reject(new Error('BRIDGE_UNAVAILABLE'));
  }

  /* ── Render: modo venda ── */

  function renderSell(sc) {
    log('renderSell', sc);
    var app = document.getElementById('app');
    if (!app) { log('ERRO: #app não encontrado'); return; }
    app.innerHTML = '';

    var card = el('article', 'sell-card');

    /* badge */
    var badge = el('span', 'vehicle-body__brand');
    badge.appendChild(txt('AVALIAÇÃO'));
    card.appendChild(badge);

    /* título */
    var titleEl = el('h3', 'vehicle-body__title');
    titleEl.appendChild(txt(sc.veiculo || 'Seu veículo'));
    card.appendChild(titleEl);

    /* specs */
    var specParts = [];
    if (sc.placa) specParts.push('Placa: ' + sc.placa);
    var kmStr = sc.km_fmt || fmtKm(sc.km) || '';
    if (kmStr) specParts.push(kmStr);
    if (specParts.length) {
      var specs = el('p', 'vehicle-body__specs');
      specs.appendChild(txt(specParts.join(' • ')));
      card.appendChild(specs);
    }

    /* proposta */
    if (sc.proposta) {
      var propLabel = el('p', 'sell-card__label');
      propLabel.appendChild(txt('Proposta Saga'));
      card.appendChild(propLabel);
      var price = el('p', 'vehicle-body__price');
      price.appendChild(txt(sc.proposta));
      card.appendChild(price);
    }

    /* hint */
    var hint = el('p', 'sell-card__hint');
    hint.appendChild(txt('📲 Informe seus dados — um consultor entra em contato via WhatsApp'));
    card.appendChild(hint);

    /* inputs */
    var nameInput = el('input', 'sell-form__input');
    nameInput.setAttribute('type', 'text');
    nameInput.setAttribute('placeholder', 'Seu nome completo');
    nameInput.setAttribute('maxlength', '100');
    nameInput.setAttribute('autocomplete', 'name');
    card.appendChild(nameInput);

    var nameErr = el('p', 'sell-form__error');
    card.appendChild(nameErr);

    var telInput = el('input', 'sell-form__input');
    telInput.setAttribute('type', 'tel');
    telInput.setAttribute('placeholder', 'Telefone com DDD');
    telInput.setAttribute('maxlength', '16');
    telInput.setAttribute('autocomplete', 'tel');
    card.appendChild(telInput);

    var telErr = el('p', 'sell-form__error');
    card.appendChild(telErr);

    /* máscara */
    telInput.addEventListener('input', function () {
      this.value = maskTel(this.value);
    });

    /* feedback */
    var feedback = el('div', 'sell-card__feedback');
    card.appendChild(feedback);

    /* botão */
    var btn = el('button', 'btn btn--primary sell-form__btn');
    btn.setAttribute('type', 'button');
    btn.appendChild(txt('Confirmar contato via WhatsApp'));

    btn.addEventListener('click', function () {
      var nome = nameInput.value.trim();
      var tel  = telInput.value.replace(/\D/g, '');

      nameErr.textContent = '';
      telErr.textContent  = '';

      if (!nome || nome.length < 2) {
        nameErr.textContent = 'Informe seu nome completo.';
        nameInput.focus();
        return;
      }
      if (tel.length < 10) {
        telErr.textContent = 'Informe um telefone com DDD (10 ou 11 dígitos).';
        telInput.focus();
        return;
      }

      btn.disabled    = true;
      btn.textContent = 'Aguarde...';

      callTool('registrar_interesse_venda', {
        nome_cliente:      nome,
        telefone_cliente:  tel,
        veiculo_descricao: sc.veiculo  || '',
        placa:             sc.placa    || '',
        km:                sc.km       || '',
        valor_proposta:    sc.proposta || '',
      })
      .then(function () {
        btn.textContent = 'Enviado ✓';
        feedback.textContent = 'Pronto, ' + nome.split(' ')[0] + '! Um consultor da Saga entrará em contato em breve via WhatsApp.';
        feedback.className = 'sell-card__feedback sell-card__feedback--ok';
      })
      .catch(function (err) {
        btn.disabled    = false;
        btn.textContent = 'Confirmar contato via WhatsApp';
        log('callTool error:', err && err.message);
        feedback.textContent = 'Não foi possível registrar agora. Tente novamente ou acesse primeiramaosaga.com.br.';
        feedback.className = 'sell-card__feedback sell-card__feedback--err';
      });
    });

    card.appendChild(btn);
    app.appendChild(card);
  }

  /* ── Render: modo compra ── */

  function renderEmpty(message) {
    var app = document.getElementById('app');
    if (!app) return;
    app.innerHTML = '';
    var div = el('div', 'empty');
    div.appendChild(txt(message || 'Nenhum veículo encontrado.'));
    app.appendChild(div);
  }

  function buildCard(vehicle) {
    var imageUrl  = safeUrl(vehicle.imageUrl || vehicle.url_imagem || vehicle.image || vehicle.foto || '');
    var linkUrl   = safeUrl(vehicle.link || vehicle.url || '');
    var title     = vehicle.title || [vehicle.brand || vehicle.marca, vehicle.model || vehicle.modelo].filter(Boolean).join(' ') || 'Veículo';
    var brand     = vehicle.brand || vehicle.marca || '';
    var year      = vehicle.year || vehicle.model_year || '';
    var km        = vehicle.kmFormatted || fmtKm(vehicle.km);
    var location  = vehicle.location || vehicle.store || [vehicle.loja, vehicle.cidade].filter(Boolean).join(' — ') || '';

    var article = el('article', 'vehicle-card');
    article.setAttribute('role', 'listitem');

    var imgWrap = el('div', 'vehicle-image');
    if (imageUrl) {
      var img = document.createElement('img');
      img.setAttribute('alt', title);
      img.setAttribute('loading', 'lazy');
      img.setAttribute('decoding', 'async');
      img.src = imageUrl;
      imgWrap.appendChild(img);
    } else {
      var placeholder = el('div', 'vehicle-image__placeholder');
      placeholder.appendChild(txt('🚗'));
      imgWrap.appendChild(placeholder);
    }
    article.appendChild(imgWrap);

    var body = el('div', 'vehicle-body');

    if (brand) {
      var brandEl = el('span', 'vehicle-body__brand');
      brandEl.appendChild(txt(brand.toUpperCase()));
      body.appendChild(brandEl);
    }

    var titleEl = el('h3', 'vehicle-body__title');
    titleEl.appendChild(txt(title));
    body.appendChild(titleEl);

    var specParts = [year ? 'Ano: ' + year : null, km || null].filter(Boolean);
    if (specParts.length) {
      var specs = el('p', 'vehicle-body__specs');
      specs.appendChild(txt(specParts.join(' • ')));
      body.appendChild(specs);
    }

    var priceEl = el('p', 'vehicle-body__price');
    priceEl.appendChild(txt(fmtPrice(vehicle.price)));
    body.appendChild(priceEl);

    if (location) {
      var locEl = el('p', 'vehicle-body__location');
      locEl.appendChild(txt('📍 ' + location));
      body.appendChild(locEl);
    }

    article.appendChild(body);

    var actions = el('div', 'vehicle-actions');
    if (linkUrl) {
      var linkBtn = el('a', 'btn btn--secondary');
      linkBtn.setAttribute('href', linkUrl);
      linkBtn.setAttribute('target', '_blank');
      linkBtn.setAttribute('rel', 'noopener noreferrer');
      linkBtn.appendChild(txt('Ver no site'));
      actions.appendChild(linkBtn);
    }
    article.appendChild(actions);
    return article;
  }

  function render(sc) {
    if (sc.mode === 'sell') { renderSell(sc); return; }

    log('render | type=' + sc.type + ' | vehicles=' + (sc.vehicles ? sc.vehicles.length : 0));
    var app = document.getElementById('app');
    if (!app) { log('ERRO: #app não encontrado'); return; }
    app.innerHTML = '';

    var vehicles = Array.isArray(sc.vehicles) ? sc.vehicles : (Array.isArray(sc.offers) ? sc.offers : []);
    log('vehicles length=' + vehicles.length);

    if (!vehicles.length) { renderEmpty('Nenhum veículo encontrado para essa busca.'); return; }

    var grid = el('div', 'vehicle-grid');
    grid.setAttribute('role', 'list');
    for (var i = 0; i < vehicles.length; i++) {
      if (vehicles[i] && typeof vehicles[i] === 'object') grid.appendChild(buildCard(vehicles[i]));
    }
    app.appendChild(grid);
    log('renderizado | ' + vehicles.length + ' cards');
  }

  /* ── Init ── */

  var _rendered = false;

  function tryRender(sc) {
    if (_rendered) return;
    _rendered = true;
    render(sc);
  }

  function init() {
    log('DOMContentLoaded');
    log('window.openai', window.openai);
    log('toolOutput', window.openai && window.openai.toolOutput);

    var payload = getToolOutput();
    log('payload inicial', payload);
    var sc = extractStructuredContent(payload);
    log('structuredContent inicial', sc);

    if (sc) { tryRender(sc); return; }

    window.addEventListener('message', function (event) {
      console.log('[vehicle-offers] postMessage | origin=' + event.origin, event.data);
      var scFromMessage = extractStructuredContent(event.data);
      if (scFromMessage) tryRender(scFromMessage);
    });

    var attempts = 0;
    var timer = setInterval(function () {
      attempts++;
      var p2 = getToolOutput();
      console.log('[vehicle-offers] polling', attempts, p2);
      var sc2 = extractStructuredContent(p2);
      if (sc2) { clearInterval(timer); tryRender(sc2); return; }
      if (attempts >= 50) {
        clearInterval(timer);
        if (!_rendered) { log('timeout'); renderEmpty('Não recebi os dados. Tente novamente.'); }
      }
    }, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
