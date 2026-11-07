// PayPal JS Web SDK v6 one-time checkout.
// Docs: https://developer.paypal.com/sdk/js/set-up
(function () {
  var root = document.getElementById("checkout");
  var statusEl = document.getElementById("checkout-status");

  function setStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.className = isError ? "status errors" : "status";
  }

  async function readError(resp) {
    try {
      var body = await resp.json();
      var d = body.detail || body;
      return (d.error || "ERROR") + (d.issue ? " (" + d.issue + ")" : "") + ": " + (d.message || resp.statusText);
    } catch (e) {
      return resp.status + " " + resp.statusText;
    }
  }

  async function createOrder() {
    var resp = await fetch("/api/paypal/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku: root.dataset.sku, quantity: 1 }),
    });
    if (!resp.ok) throw new Error(await readError(resp));
    var order = await resp.json();
    return { orderId: order.id };
  }

  async function onApprove(data) {
    setStatus("Completing your payment...");
    var resp = await fetch("/api/paypal/orders/" + encodeURIComponent(data.orderId) + "/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) {
      setStatus("Payment could not be completed. " + (await readError(resp)), true);
      return;
    }
    var result = await resp.json();
    window.location.href =
      root.dataset.thanksUrl +
      "?order=" + encodeURIComponent(result.order_id) +
      "&capture=" + encodeURIComponent(result.capture_id);
  }

  window.onPayPalFailed = function () {
    setStatus("Could not load PayPal. Please refresh the page.", true);
  };

  // Extra payment buttons (Venmo, Pay Later, card) next to the PayPal button; each is wired only if the page has it.
  var EXTRA_BUTTONS = [
    { id: "venmo-button", method: "venmo", create: "createVenmoOneTimePaymentSession" },
    { id: "pay-later-button", method: "paylater", create: "createPayLaterOneTimePaymentSession" },
    { id: "card-button", method: "card", create: "createPayPalGuestOneTimePaymentSession" },
  ];

  function sessionCallbacks() {
    return {
      onApprove: onApprove,
      onCancel: function () { setStatus("Payment cancelled. You have not been charged."); },
      onError: function (err) { setStatus("PayPal error: " + (err && err.message ? err.message : err), true); },
    };
  }

  function wireButton(button, session) {
    button.removeAttribute("hidden");
    button.addEventListener("click", async function () {
      setStatus("");
      try {
        // Pass the promise, do not await createOrder() first: awaiting breaks the popup's transient activation.
        await session.start({ presentationMode: "auto" }, createOrder());
      } catch (err) {
        setStatus("Could not start PayPal checkout. " + err.message, true);
      }
    });
  }

  async function createInstance(components) {
    return window.paypal.createInstance({
      clientId: root.dataset.clientId,
      components: components,
      pageType: root.dataset.pageType || "checkout",
    });
  }

  window.onPayPalLoaded = async function () {
    try {
      var components = (root.dataset.components || "paypal-payments").split(",");
      var sdk;
      try {
        sdk = await createInstance(components);
      } catch (err) {
        if (components.length < 2) throw err;
        components = ["paypal-payments"];  // an optional component was refused: keep plain PayPal working
        sdk = await createInstance(components);
      }
      var methods = await sdk.findEligibleMethods({ currencyCode: "USD" });

      var message = document.getElementById("pay-later-message");
      if (message && components.indexOf("paypal-messages") >= 0) {
        try {
          var content = await sdk.createPayPalMessages().fetchContent({
            amount: message.dataset.amount,
            currencyCode: "USD",
          });
          message.setContent(content);
        } catch (err) { /* the message is optional */ }
      }

      var button = document.getElementById("paypal-button");
      if (!button) return;
      if (!methods.isEligible("paypal")) {
        setStatus("PayPal is not available for this purchase.", true);
        return;
      }
      wireButton(button, await sdk.createPayPalOneTimePaymentSession(sessionCallbacks()));

      for (var i = 0; i < EXTRA_BUTTONS.length; i++) {
        var extra = EXTRA_BUTTONS[i];
        var el = document.getElementById(extra.id);
        if (!el || !methods.isEligible(extra.method) || typeof sdk[extra.create] !== "function") continue;
        try {
          wireButton(el, await sdk[extra.create](sessionCallbacks()));
        } catch (err) { /* an optional payment method that cannot start stays hidden */ }
      }
    } catch (err) {
      setStatus("PayPal failed to initialize: " + err.message, true);
    }
  };
})();
