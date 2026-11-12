// GhostShopper WebMCP recorder, injected before any page script (Playwright add_init_script).
// Records every tool a page registers in window.__ghostWebMCP. A browser with native WebMCP keeps its own
// modelContext (its registerTool is only wrapped to record); otherwise a small test shim stands in for it.
(function () {
  'use strict';
  if (window.__ghostWebMCP) return;

  var state = { native: false, tools: {}, context: null, shimmed: [] };
  window.__ghostWebMCP = state;

  function record(tool) {
    if (tool && typeof tool.name === 'string' && typeof tool.execute === 'function') state.tools[tool.name] = tool;
  }

  function wrap(target) {
    var original = target.registerTool.bind(target);
    target.registerTool = function (tool) {
      record(tool);
      return original.apply(null, arguments);
    };
    if (typeof target.provideContext === 'function') {
      var provide = target.provideContext.bind(target);
      target.provideContext = function (context) {
        state.context = context;
        return provide.apply(null, arguments);
      };
    }
  }

  var native = [document.modelContext, navigator.modelContext, navigator.modelContextTesting].filter(function (c) {
    return c && typeof c.registerTool === 'function';
  });

  if (native.length) {
    state.native = true;
    native.forEach(wrap);
    return;
  }

  var shim = {
    registerTool: function (tool) { record(tool); },
    unregisterTool: function (name) { delete state.tools[typeof name === 'string' ? name : name && name.name]; },
    provideContext: function (context) { state.context = context; },
  };
  function define(target, key) {
    try { Object.defineProperty(target, key, { value: shim, configurable: true }); state.shimmed.push(key); } catch (err) { /* read-only */ }
  }
  define(navigator, 'modelContext');
  define(document, 'modelContext');
})();
