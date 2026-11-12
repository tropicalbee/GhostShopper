// GhostShopper's adapter implementing the shopping.* tool contract that PayPal's WebMCP showcase registers.
// This is not PayPal's WebMCP service: it registers the same four tools, with the same input schemas, annotations and
// result envelope, but they are answered by this demo store (POST <store>/webmcp/rpc), not by PayPal.
(function () {
  'use strict';

  var script = document.currentScript;
  var rpcUrl = new URL(script.dataset.rpc, window.location.href).href;
  var last = { cartId: '', token: '' };
  var registeredByContext = new WeakMap();
  var inFlight = false;

  function currentProductId() {
    var match = window.location.pathname.match(/\/products\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function modelContexts() {
    var candidates = [document.modelContext, navigator.modelContext, navigator.modelContextTesting];
    return Array.from(new Set(candidates.filter(function (ctx) { return ctx && typeof ctx.registerTool === 'function'; })));
  }

  function envelope(result) {
    return { content: [{ type: 'text', text: JSON.stringify(result || {}) }], structuredContent: result || {} };
  }

  function approvalWindow(name) {
    if (name !== 'shopping.initiateCheckout') return null;
    var win = window.open('', 'paypal-webmcp-approval', 'popup=yes,width=600,height=700,resizable=yes,scrollbars=yes');
    if (win) {
      try { win.document.body.textContent = 'Connecting to PayPal...'; } catch (err) { /* cross-origin */ }
    }
    return win;
  }

  async function callRpc(name, args) {
    var input = Object.assign({}, args || {});
    if (name === 'shopping.getProduct' || name === 'shopping.initiateCheckout') {
      if (!input.product_id && currentProductId()) input.product_id = currentProductId();
    }
    if (name === 'shopping.completeCheckout') {
      if (!input.cart_id) input.cart_id = last.cartId;
      if (!input.token) input.token = last.token;
    }
    var popup = approvalWindow(name);
    var res = await fetch(rpcUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 'webmcp-' + Date.now(), tool: name, input: input }),
    });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.error) {
      if (popup && !popup.closed) popup.close();
      throw new Error((data.error && data.error.message) || 'WebMCP tool call failed');
    }
    var result = data.result;
    if (result && result.cart_id) last.cartId = String(result.cart_id);
    if (result && result.approval_url) {
      try { last.token = new URL(result.approval_url).searchParams.get('token') || last.token; } catch (err) { /* keep the old token */ }
      if (popup) {
        try { popup.location.replace(result.approval_url); } catch (err) { popup.location.href = result.approval_url; }
      }
    } else if (popup && !popup.closed) {
      popup.close();
    }
    return envelope(result);
  }

  function tools() {
    return [
      {
        name: 'shopping.searchProducts',
        description: 'Search the Fernhill Ceramics storefront for products.',
        annotations: { readOnlyHint: true },
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            query: { type: 'string', description: 'Search query, such as mug, vase, bowl or stoneware.' },
            max_results: { type: 'integer', minimum: 1, maximum: 20 },
            category: { type: 'string' },
          },
          required: ['query'],
        },
        execute: function (args) { return callRpc('shopping.searchProducts', args); },
      },
      {
        name: 'shopping.getProduct',
        description: 'Get details for a Fernhill Ceramics product. On a product page, product_id can be omitted.',
        annotations: { readOnlyHint: true },
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            product_id: { type: 'string', description: 'Product ID. Defaults to the current product page when available.' },
          },
          required: [],
        },
        execute: function (args) { return callRpc('shopping.getProduct', args); },
      },
      {
        name: 'shopping.initiateCheckout',
        description: 'Create a PayPal checkout for one Fernhill Ceramics product and open the PayPal approval window. User approval is required before payment completes.',
        annotations: { readOnlyHint: false },
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            product_id: { type: 'string', description: 'Product ID. Defaults to the current product page when available.' },
            quantity: { type: 'integer', minimum: 1, maximum: 5, description: 'Quantity to buy. Defaults to 1.' },
            buyer_email: { type: 'string', description: 'Optional email for the order confirmation.' },
            requires_user_approval: { type: 'boolean', description: 'Must be true. Checkout opens PayPal for buyer approval.' },
          },
          required: [],
        },
        execute: function (args) { return callRpc('shopping.initiateCheckout', args); },
      },
      {
        name: 'shopping.completeCheckout',
        description: 'Complete a PayPal checkout after buyer approval. Uses the last WebMCP cart and token when omitted.',
        annotations: { readOnlyHint: false },
        inputSchema: {
          type: 'object',
          additionalProperties: false,
          properties: { cart_id: { type: 'string' }, token: { type: 'string' } },
          required: [],
        },
        execute: function (args) { return callRpc('shopping.completeCheckout', args); },
      },
    ];
  }

  async function registerTool(ctx, tool) {
    var done = registeredByContext.get(ctx);
    if (!done) registeredByContext.set(ctx, (done = new Set()));
    if (done.has(tool.name)) return false;
    try {
      await Promise.resolve(ctx.registerTool(tool));
      done.add(tool.name);
      return true;
    } catch (err) {
      console.warn('[fernhill-webmcp] registerTool failed', tool.name, err);
      return false;
    }
  }

  async function registerAll() {
    var contexts = modelContexts();
    if (!contexts.length) return false;
    var list = tools();
    var results = await Promise.all(contexts.flatMap(function (ctx) {
      if (typeof ctx.provideContext === 'function') {
        try {
          ctx.provideContext({ '@type': 'WebPage', name: document.title, url: window.location.href, storeId: 'fernhill-ceramics', productId: currentProductId() || undefined });
        } catch (err) { /* context is optional */ }
      }
      return list.map(function (tool) { return registerTool(ctx, tool); });
    }));
    var all = contexts.every(function (ctx) {
      var done = registeredByContext.get(ctx);
      return done && list.every(function (tool) { return done.has(tool.name); });
    });
    if (results.some(Boolean) || all) window.dispatchEvent(new Event('webmcp:tools-updated'));
    return all;
  }

  var attempts = 0;
  var timer = window.setInterval(boot, 250);
  function boot() {
    attempts += 1;
    if (inFlight) return;
    inFlight = true;
    registerAll()
      .then(function (all) { if (all || attempts >= 80) window.clearInterval(timer); })
      .catch(function () { if (attempts >= 80) window.clearInterval(timer); })
      .finally(function () { inFlight = false; });
  }
  boot();
})();
