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

  window.onPayPalLoaded = async function () {
    try {
      var sdk = await window.paypal.createInstance({
        clientId: root.dataset.clientId,
        components: ["paypal-payments"],
        pageType: "checkout",
      });
      var methods = await sdk.findEligibleMethods({ currencyCode: "USD" });
      if (!methods.isEligible("paypal")) {
        setStatus("PayPal is not available for this purchase.", true);
        return;
      }
      var session = await sdk.createPayPalOneTimePaymentSession({
        onApprove: onApprove,
        onCancel: function () { setStatus("Payment cancelled. You have not been charged."); },
        onError: function (err) { setStatus("PayPal error: " + (err && err.message ? err.message : err), true); },
      });
      var button = document.getElementById("paypal-button");
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
    } catch (err) {
      setStatus("PayPal failed to initialize: " + err.message, true);
    }
  };
})();
