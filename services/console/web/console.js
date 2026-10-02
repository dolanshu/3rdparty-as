(() => {
  const isPreview = new URLSearchParams(window.location.search).get("preview") === "1";
  const API_BASE = "/internal/v1";

  const rules = [
    {
      id: "R-104",
      name: "Hong Kong mobile translation",
      matchField: "Called party",
      matchType: "Prefix",
      matchValue: "+86755",
      target: "Translation",
      targetDetail: "+852755*",
      enabled: true,
      version: "v18",
      updatedAt: "2026-09-30 14:22 UTC",
    },
    {
      id: "R-108",
      name: "High-risk international block",
      matchField: "Calling party",
      matchType: "Prefix",
      matchValue: "+882",
      target: "Anti-fraud",
      targetDetail: "risk policy IF-04",
      enabled: true,
      version: "v07",
      updatedAt: "2026-09-29 08:10 UTC",
    },
    {
      id: "R-117",
      name: "Premium destination route",
      matchField: "Called party",
      matchType: "Regex",
      matchValue: "^\\+852\\d{8}$",
      target: "Routing",
      targetDetail: "trunk hk-premium",
      enabled: false,
      version: "v11",
      updatedAt: "2026-09-26 17:41 UTC",
    },
    {
      id: "R-123",
      name: "Default destination route",
      matchField: "Called party",
      matchType: "Prefix",
      matchValue: "+",
      target: "Default",
      targetDetail: "route pool default",
      enabled: true,
      version: "v03",
      updatedAt: "2026-09-25 11:06 UTC",
    },
  ];

  const copyRule = (rule) => (rule ? { ...rule } : null);
  const state = {
    rules,
    changeOrders: [
      {
        id: "CO-2418",
        action: "Update",
        ruleId: "R-104",
        ruleName: "Hong Kong mobile translation",
        requestedBy: "Preview fixture",
        submittedAt: "2026-10-01 09:16 UTC",
        status: "Pending",
        before: copyRule(rules[0]),
        payload: { ...rules[0], targetDetail: "+8527551*" },
        reason: "",
      },
      {
        id: "CO-2416",
        action: "Create",
        ruleId: "R-131",
        ruleName: "Weekend fraud burst",
        requestedBy: "Preview fixture",
        submittedAt: "2026-10-01 08:52 UTC",
        status: "Pending",
        before: null,
        payload: {
          id: "R-131",
          name: "Weekend fraud burst",
          matchField: "Calling party",
          matchType: "Prefix",
          matchValue: "+881",
          target: "Anti-fraud",
          targetDetail: "risk policy IF-09",
          enabled: true,
          version: "v01",
          updatedAt: "Preview session",
        },
        reason: "",
      },
      {
        id: "CO-2412",
        action: "Enable",
        ruleId: "R-117",
        ruleName: "Premium destination route",
        requestedBy: "Preview fixture",
        submittedAt: "2026-10-01 08:14 UTC",
        status: "Pending",
        before: copyRule(rules[2]),
        payload: { ...rules[2], enabled: true },
        reason: "",
      },
      {
        id: "CO-2403",
        action: "Update",
        ruleId: "R-108",
        ruleName: "High-risk international block",
        requestedBy: "Preview fixture",
        submittedAt: "2026-09-30 16:08 UTC",
        status: "Rejected",
        before: copyRule(rules[1]),
        payload: { ...rules[1], targetDetail: "risk policy IF-08" },
        reason: "Policy review required before changing this target.",
        decidedAt: "2026-09-30 16:32 UTC",
      },
      {
        id: "CO-2398",
        action: "Update",
        ruleId: "R-123",
        ruleName: "Default destination route",
        requestedBy: "Preview fixture",
        submittedAt: "2026-09-29 10:21 UTC",
        status: "Approved",
        before: copyRule(rules[3]),
        payload: { ...rules[3], targetDetail: "route pool default" },
        reason: "",
        decidedAt: "2026-09-29 10:38 UTC",
      },
    ],
    traces: [
      {
        callId: "7f1c8b31-3f4b-4e70@edge.ims.example",
        startedAt: "2026-10-01 10:39:14 UTC",
        outcome: "200 OK",
        from: "+85261234567",
        to: "+8527551234567",
        rule: "R-104 · v18",
        messages: [
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:39:14.238", direction: "IN", method: "INVITE", response: "—", from: "+85261234567", to: "+867551234567", detail: "INVITE received on inbound UAS leg" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:39:14.244", direction: "OUT", method: "INVITE", response: "—", from: "+85261234567", to: "+8527551234567", detail: "INVITE sent on outbound UAC leg; translated by R-104 · v18" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:39:14.250", direction: "IN", method: "INVITE", response: "100 Trying", from: "+85261234567", to: "+8527551234567", detail: "100 Trying received from downstream UAS" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:39:14.256", direction: "OUT", method: "INVITE", response: "100 Trying", from: "+85261234567", to: "+867551234567", detail: "100 Trying forwarded to upstream UAC" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:39:14.611", direction: "IN", method: "INVITE", response: "180 Ringing", from: "+85261234567", to: "+8527551234567", detail: "180 Ringing received from downstream UAS" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:39:14.614", direction: "OUT", method: "INVITE", response: "180 Ringing", from: "+85261234567", to: "+867551234567", detail: "180 Ringing forwarded to upstream UAC" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:39:14.698", direction: "IN", method: "INVITE", response: "200 OK", from: "+85261234567", to: "+8527551234567", detail: "200 OK received from downstream UAS" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:39:14.702", direction: "OUT", method: "INVITE", response: "200 OK", from: "+85261234567", to: "+867551234567", detail: "200 OK forwarded to upstream UAC" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:39:14.710", direction: "IN", method: "ACK", response: "—", from: "+85261234567", to: "+867551234567", detail: "ACK received from upstream UAC on inbound UAS leg" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:39:14.716", direction: "OUT", method: "ACK", response: "—", from: "+85261234567", to: "+8527551234567", detail: "ACK sent to downstream UAS on outbound UAC leg" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:41:08.104", direction: "IN", method: "BYE", response: "—", from: "+85261234567", to: "+867551234567", detail: "BYE received from upstream UAC on inbound UAS leg" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:41:08.111", direction: "OUT", method: "BYE", response: "—", from: "+85261234567", to: "+8527551234567", detail: "BYE sent to downstream UAS on outbound UAC leg" },
          { callId: "7f1c8b31-3f4b-4e70-uac@edge.ims.example", time: "10:41:08.119", direction: "IN", method: "BYE", response: "200 OK", from: "+85261234567", to: "+8527551234567", detail: "200 OK received from downstream UAS for outbound BYE" },
          { callId: "7f1c8b31-3f4b-4e70@edge.ims.example", time: "10:41:08.126", direction: "OUT", method: "BYE", response: "200 OK", from: "+85261234567", to: "+867551234567", detail: "200 OK forwarded to upstream UAC for inbound BYE" },
        ],
      },
      {
        callId: "b84d2a90-7c13-41e4@edge.ims.example",
        startedAt: "2026-10-01 10:34:02 UTC",
        outcome: "603 Decline",
        from: "+88213005501",
        to: "+85291230000",
        rule: "R-108 · v07",
        messages: [
          { callId: "b84d2a90-7c13-41e4@edge.ims.example", time: "10:34:02.009", direction: "IN", method: "INVITE", response: "—", from: "+88213005501", to: "+85291230000", detail: "Ingress received from S-CSCF" },
          { callId: "b84d2a90-7c13-41e4@edge.ims.example", time: "10:34:02.013", direction: "OUT", method: "INVITE", response: "603 Decline", from: "+88213005501", to: "+85291230000", detail: "603 Decline sent upstream; rejected by anti-fraud policy IF-04" },
          { callId: "b84d2a90-7c13-41e4@edge.ims.example", time: "10:34:02.016", direction: "IN", method: "ACK", response: "—", from: "+88213005501", to: "+85291230000", detail: "ACK received from upstream UAC" },
        ],
      },
      {
        callId: "d22a8904-1cc7-4fb0@edge.ims.example",
        startedAt: "2026-10-01 10:29:47 UTC",
        outcome: "487 Request Terminated",
        from: "+85269990011",
        to: "+852755009988",
        rule: "R-104 · v18",
        messages: [
          { callId: "d22a8904-1cc7-4fb0@edge.ims.example", time: "10:29:47.101", direction: "IN", method: "INVITE", response: "—", from: "+85269990011", to: "+86755009988", detail: "INVITE received on inbound UAS leg" },
          { callId: "d22a8904-1cc7-4fb0-uac@edge.ims.example", time: "10:29:47.109", direction: "OUT", method: "INVITE", response: "—", from: "+85269990011", to: "+852755009988", detail: "INVITE sent on outbound UAC leg; translated by R-104 · v18" },
          { callId: "d22a8904-1cc7-4fb0@edge.ims.example", time: "10:29:47.287", direction: "IN", method: "CANCEL", response: "—", from: "+85269990011", to: "+86755009988", detail: "CANCEL received from upstream for the inbound INVITE transaction" },
          { callId: "d22a8904-1cc7-4fb0@edge.ims.example", time: "10:29:47.290", direction: "OUT", method: "CANCEL", response: "200 OK", from: "+85269990011", to: "+86755009988", detail: "200 OK sent upstream for the inbound CANCEL transaction" },
          { callId: "d22a8904-1cc7-4fb0-uac@edge.ims.example", time: "10:29:47.293", direction: "OUT", method: "CANCEL", response: "—", from: "+85269990011", to: "+852755009988", detail: "CANCEL sent downstream for the outbound INVITE transaction" },
          { callId: "d22a8904-1cc7-4fb0-uac@edge.ims.example", time: "10:29:47.296", direction: "IN", method: "CANCEL", response: "200 OK", from: "+85269990011", to: "+852755009988", detail: "200 OK received from downstream for the outbound CANCEL transaction" },
          { callId: "d22a8904-1cc7-4fb0-uac@edge.ims.example", time: "10:29:47.301", direction: "IN", method: "INVITE", response: "487 Request Terminated", from: "+85269990011", to: "+852755009988", detail: "487 received from downstream for the outbound INVITE transaction" },
          { callId: "d22a8904-1cc7-4fb0-uac@edge.ims.example", time: "10:29:47.304", direction: "OUT", method: "ACK", response: "—", from: "+85269990011", to: "+852755009988", detail: "ACK sent downstream for the non-2xx outbound INVITE response" },
          { callId: "d22a8904-1cc7-4fb0@edge.ims.example", time: "10:29:47.307", direction: "OUT", method: "INVITE", response: "487 Request Terminated", from: "+85269990011", to: "+86755009988", detail: "487 forwarded upstream for the inbound INVITE transaction" },
          { callId: "d22a8904-1cc7-4fb0@edge.ims.example", time: "10:29:47.314", direction: "IN", method: "ACK", response: "—", from: "+85269990011", to: "+86755009988", detail: "ACK received from upstream for the inbound INVITE transaction" },
        ],
      },
    ],
  };

  if (!isPreview) {
    state.rules = [];
    state.changeOrders = [];
    state.traces = [];
  }

  let nextRuleNumber = 132;
  let nextOrderNumber = 2420;
  let editingRuleId = null;
  let selectedOrderId = null;
  let selectedTraceId = state.traces[0]?.callId || null;
  let traceQuery = "";
  const liveData = { rules: "loading", orders: "loading" };
  let authenticated = false;
  let sessionUserId = null;
  let sessionRoles = [];

  const viewCopy = {
    rules: { title: "Rule registry", description: isPreview ? "Review rule state and submit changes for approval." : "Review current managed-rule records and their revisions." },
    "change-orders": { title: "Change orders", description: isPreview ? "Review proposed changes; decisions here affect local preview data only." : "Track change-order state through approval and distribution." },
    "call-traces": { title: "Call traces", description: "Search fixture message traces by Call-ID." },
    operations: { title: "Operations", description: "Inspect representative fixture metrics and instance state." },
  };

  const elements = {
    pageTitle: document.querySelector("#page-title"),
    pageDescription: document.querySelector("#page-description"),
    createRuleButton: document.querySelector("#create-rule-button"),
    previewBanner: document.querySelector("#preview-banner"),
    environmentLabel: document.querySelector("#environment-label"),
    loginButton: document.querySelector("#login-button"),
    logoutButton: document.querySelector("#logout-button"),
    identityUser: document.querySelector("#identity-user"),
    identityRoles: document.querySelector("#identity-roles"),
    liveStatus: document.querySelector("#live-status"),
    liveStatusMessage: document.querySelector("#live-status-message"),
    reloadDataButton: document.querySelector("#reload-data-button"),
    loginDialog: document.querySelector("#login-dialog"),
    loginForm: document.querySelector("#login-form"),
    loginUserId: document.querySelector("#login-user-id"),
    loginPassword: document.querySelector("#login-password"),
    loginError: document.querySelector("#login-error"),
    loginSubmit: document.querySelector("#login-submit"),
    rulesTable: document.querySelector("#rules-table-body"),
    ruleSearch: document.querySelector("#rule-search"),
    ruleStateFilter: document.querySelector("#rule-state-filter"),
    ruleTotal: document.querySelector("#rule-total"),
    rulePendingTotal: document.querySelector("#rule-pending-total"),
    ruleResultCount: document.querySelector("#rule-result-count"),
    rulesNavCount: document.querySelector("#rules-nav-count"),
    ruleRevisionHeading: document.querySelector("#rule-revision-heading"),
    ruleTotalLabel: document.querySelector("#rule-total-label"),
    rulePendingLabel: document.querySelector("#rule-pending-label"),
    rulesDescription: document.querySelector("#rules-description"),
    ordersTable: document.querySelector("#orders-table-body"),
    orderSearch: document.querySelector("#order-search"),
    orderStateFilter: document.querySelector("#order-state-filter"),
    ordersPendingTotal: document.querySelector("#orders-pending-total"),
    ordersResultCount: document.querySelector("#orders-result-count"),
    ordersNavCount: document.querySelector("#orders-nav-count"),
    ordersDescription: document.querySelector("#orders-description"),
    ordersPendingLabel: document.querySelector("#orders-pending-label"),
    orderCreatedHeading: document.querySelector("#order-created-heading"),
    orderStateHeading: document.querySelector("#order-state-heading"),
    tracesDescription: document.querySelector("#traces-description"),
    tracesUnavailable: document.querySelector("#traces-unavailable"),
    operationsDescription: document.querySelector("#operations-description"),
    operationsUnavailable: document.querySelector("#operations-unavailable"),
    operationsPendingTotal: document.querySelector("#operations-pending-total"),
    traceSearchForm: document.querySelector("#trace-search-form"),
    traceSearch: document.querySelector("#trace-search"),
    traceResultSummary: document.querySelector("#trace-result-summary"),
    traceListCount: document.querySelector("#trace-list-count"),
    traceResults: document.querySelector("#trace-results-body"),
    traceDetail: document.querySelector("#trace-detail-body"),
    traceMessageCount: document.querySelector("#trace-message-count"),
    ruleDialog: document.querySelector("#rule-dialog"),
    ruleForm: document.querySelector("#rule-form"),
    ruleDialogTitle: document.querySelector("#rule-dialog-title"),
    ruleName: document.querySelector("#rule-name"),
    ruleMatchValue: document.querySelector("#rule-match-value"),
    ruleMatchType: document.querySelector("#rule-match-type"),
    ruleTargetDetail: document.querySelector("#rule-target-detail"),
    reviewDialog: document.querySelector("#review-dialog"),
    reviewTitle: document.querySelector("#review-dialog-title"),
    reviewMeta: document.querySelector("#review-meta"),
    reviewCurrent: document.querySelector("#review-current"),
    reviewProposed: document.querySelector("#review-proposed"),
    reviewStatus: document.querySelector("#review-status"),
    reviewActions: document.querySelector("#review-actions"),
    rejectForm: document.querySelector("#reject-form"),
    rejectReason: document.querySelector("#reject-reason"),
    toastRegion: document.querySelector("#toast-region"),
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);
  }

  function statusBadge(status, label = status) {
    const classes = {
      Enabled: "status-enabled",
      Disabled: "status-disabled",
      Pending: "status-pending",
      Approved: "status-approved",
      Rejected: "status-rejected",
      Healthy: "status-healthy",
      Tombstone: "status-neutral",
      draft: "status-pending",
      submitted: "status-pending",
      approved: "status-approved",
      distributing: "status-info",
      applied: "status-enabled",
      rejected: "status-rejected",
      rolled_back: "status-neutral",
    };
    return `<span class="status-badge ${classes[status] || "status-neutral"}">${escapeHtml(label)}</span>`;
  }

  function liveStatusLabel(status) {
    return ({ rolled_back: "Rolled back" })[status] || status.charAt(0).toUpperCase() + status.slice(1);
  }

  function isAwaitingDecision(order) {
    return isPreview ? order.status === "Pending" : order.status === "draft" || order.status === "submitted";
  }

  function liveOrderAction(order) {
    const roles = new Set(sessionRoles.map((role) => String(role).toLowerCase()));
    const canSubmit = ["operator", "approver", "admin"].some((role) => roles.has(role));
    const canApprove = ["approver", "admin"].some((role) => roles.has(role));
    if (order.status === "draft" && order.createdBy === sessionUserId && canSubmit) return "submit";
    if (order.status === "submitted" && order.createdBy && order.createdBy !== sessionUserId && canApprove) return "review";
    return "details";
  }

  function pendingOrderFor(ruleId) {
    return state.changeOrders.find((order) => order.ruleId === ruleId && isAwaitingDecision(order)) || null;
  }

  function visibleRuleRows() {
    const rows = state.rules.map((rule) => ({ ...rule, pendingOrder: pendingOrderFor(rule.id) }));
    const liveIds = new Set(state.rules.map((rule) => rule.id));
    const pendingCreates = state.changeOrders
      .filter((order) => isAwaitingDecision(order) && order.action === "Create" && !liveIds.has(order.ruleId))
      .map((order) => ({ ...order.payload, pendingOrder: order }));
    return [...rows, ...pendingCreates];
  }

  function formatMatch(rule) {
    return `${rule.matchField} · ${rule.matchType}`;
  }

  function renderRuleRow(rule) {
    const pending = rule.pendingOrder;
    const status = rule.isTombstone
      ? statusBadge("Tombstone", "Deleted record")
      : pending?.action === "Create"
        ? `<span class="status-badge status-pending">Pending creation</span>`
        : `<div class="status-stack">${statusBadge(rule.enabled ? "Enabled" : "Disabled")}${pending ? `<span class="status-badge status-pending">Pending ${escapeHtml(pending.action.toLowerCase())}</span>` : ""}</div>`;
    const actions = !isPreview
      ? ""
      : pending
      ? `<button class="button-link" type="button" data-open-order="${escapeHtml(pending.id)}">Review request</button>`
      : `<div class="row-actions">
          <button class="button-link" type="button" data-rule-action="edit" data-rule-id="${escapeHtml(rule.id)}">Edit</button>
          <button class="button-link" type="button" data-rule-action="toggle" data-rule-id="${escapeHtml(rule.id)}">Queue ${rule.enabled ? "disable" : "enable"}</button>
          <button class="button-link" type="button" data-rule-action="delete" data-rule-id="${escapeHtml(rule.id)}">Queue delete</button>
        </div>`;

    return `<tr>
      <td class="primary-cell"><strong>${escapeHtml(rule.name)}</strong><small class="mono">${escapeHtml(rule.id)}</small></td>
      <td class="match-cell"><span>${escapeHtml(formatMatch(rule))}</span><small><code>${escapeHtml(rule.matchValue)}</code></small></td>
      <td class="secondary-cell"><strong>${escapeHtml(rule.target)}</strong><small>${escapeHtml(rule.targetDetail)}</small></td>
      <td>${status}</td>
      <td class="secondary-cell"><strong class="mono">${isPreview ? escapeHtml(rule.version) : `rev ${escapeHtml(rule.revision)}`}</strong><small>${escapeHtml(isPreview ? rule.updatedAt : "Managed record")}</small></td>
      <td>${actions}</td>
    </tr>`;
  }

  function renderRules() {
    const query = elements.ruleSearch.value.trim().toLowerCase();
    const stateFilter = elements.ruleStateFilter.value;
    const allRows = visibleRuleRows();
    const rows = allRows.filter((rule) => {
      const searchable = [rule.id, rule.name, rule.matchField, rule.matchType, rule.matchValue, rule.target, rule.targetDetail].join(" ").toLowerCase();
      const matchesQuery = !query || searchable.includes(query);
      const hasPendingChange = isPreview
        ? Boolean(rule.pendingOrder)
        : state.changeOrders.some((order) => isAwaitingDecision(order) && order.ruleId === rule.id);
      const matchesState = stateFilter === "all"
        || (stateFilter === "pending" && hasPendingChange)
        || (stateFilter === "enabled" && rule.enabled && rule.pendingOrder?.action !== "Create")
        || (stateFilter === "disabled" && !rule.enabled && rule.pendingOrder?.action !== "Create");
      return matchesQuery && matchesState;
    });

    const ruleState = !isPreview && liveData.rules !== "ready"
      ? liveData.rules === "loading" ? "Loading managed rules…" : liveData.rules === "unauthenticated" ? "Sign in to load managed rules." : "Managed rules could not be loaded. Retry the request."
      : null;
    elements.rulesTable.innerHTML = ruleState
      ? `<tr class="row-empty"><td colspan="6">${escapeHtml(ruleState)}</td></tr>`
      : rows.length
      ? rows.map(renderRuleRow).join("")
      : `<tr class="row-empty"><td colspan="6">${isPreview ? "No rules match these filters." : allRows.length ? "No rules match these filters." : "No managed-rule records returned."}</td></tr>`;
    elements.ruleTotal.textContent = String(allRows.length);
    elements.rulePendingTotal.textContent = String(state.changeOrders.filter(isAwaitingDecision).length);
    elements.ruleResultCount.textContent = `${rows.length} ${rows.length === 1 ? "entry" : "entries"}`;
    elements.rulesNavCount.textContent = String(visibleRuleRows().length);
  }

  function renderChangeOrders() {
    const query = elements.orderSearch.value.trim().toLowerCase();
    const decision = elements.orderStateFilter.value;
    const rows = state.changeOrders.filter((order) => {
      const searchable = [order.id, order.action, order.ruleId, order.ruleName, order.requestedBy, order.status].join(" ").toLowerCase();
      return (!query || searchable.includes(query)) && (decision === "all" || order.status === decision);
    });

    const ordersState = !isPreview && liveData.orders !== "ready"
      ? liveData.orders === "loading" ? "Loading change orders…" : liveData.orders === "unauthenticated" ? "Sign in to load change orders." : "Change orders could not be loaded. Retry the request."
      : null;
    elements.ordersTable.innerHTML = ordersState
      ? `<tr class="row-empty"><td colspan="6">${escapeHtml(ordersState)}</td></tr>`
      : rows.length
      ? rows.map((order) => isPreview ? `<tr>
          <td class="primary-cell"><button class="button-link mono" type="button" data-open-order="${escapeHtml(order.id)}" aria-label="Review change order ${escapeHtml(order.id)}">${escapeHtml(order.id)}</button><small>${escapeHtml(order.action)} rule</small></td>
          <td class="secondary-cell"><strong>${escapeHtml(order.ruleName)}</strong><small class="mono">${escapeHtml(order.ruleId)}</small></td>
          <td>${escapeHtml(order.requestedBy)}</td>
          <td class="mono">${escapeHtml(order.submittedAt)}</td>
          <td>${statusBadge(order.status)}</td>
          <td><button class="button-link" type="button" data-open-order="${escapeHtml(order.id)}">${order.status === "Pending" ? "Review" : "Details"}</button></td>
        </tr>` : `<tr>
          <td class="primary-cell"><strong class="mono">${escapeHtml(order.id)}</strong><small>Revision ${escapeHtml(order.revision)} · ${escapeHtml(order.action)}</small></td>
          <td class="secondary-cell"><strong>${escapeHtml(order.ruleName)}</strong><small class="mono">${escapeHtml(order.ruleId)}</small></td>
          <td>${escapeHtml(order.requestedBy)}</td>
          <td class="mono">${escapeHtml(order.createdAt)}</td>
          <td>${statusBadge(order.status, liveStatusLabel(order.status))}</td>
          <td><button class="button-link" type="button" data-open-order="${escapeHtml(order.id)}">${liveOrderAction(order) === "submit" ? "Submit" : liveOrderAction(order) === "review" ? "Review" : "Details"}</button></td>
        </tr>`).join("")
      : `<tr class="row-empty"><td colspan="6">${isPreview ? "No change orders match these filters." : "No change orders returned."}</td></tr>`;

    const pendingCount = state.changeOrders.filter(isAwaitingDecision).length;
    elements.ordersPendingTotal.textContent = String(pendingCount);
    if (isPreview) elements.operationsPendingTotal.textContent = String(pendingCount);
    elements.ordersResultCount.textContent = String(rows.length);
    elements.ordersNavCount.textContent = String(pendingCount);
  }

  function matchingTraces() {
    const query = traceQuery.toLowerCase();
    return state.traces.filter((trace) =>
      traceCallIds(trace).some((callId) => callId.toLowerCase().includes(query)));
  }

  function traceCallIds(trace) {
    return [...new Set([trace.callId, ...trace.messages.map((message) => message.callId || trace.callId)])];
  }

  function renderTraceDetail(trace) {
    if (!trace) {
      elements.traceDetail.innerHTML = `<div class="empty-state"><strong>No trace selected</strong><p>Choose a Call-ID from the results to inspect its fixture message sequence.</p></div>`;
      elements.traceMessageCount.textContent = "";
      return;
    }

    const callIds = traceCallIds(trace);
    elements.traceMessageCount.textContent = `${trace.messages.length} messages`;
    elements.traceDetail.innerHTML = `<div class="trace-identity">
      <p>Trace lookup key: <code>${escapeHtml(trace.callId)}</code></p>
      <p>Call-IDs in trace: ${callIds.map((callId) => `<code>${escapeHtml(callId)}</code>`).join(" · ")}</p>
        <p>${escapeHtml(trace.startedAt)} · ${escapeHtml(trace.outcome)} · Rule ${escapeHtml(trace.rule)}</p>
      </div>
      <div class="table-scroll trace-message-scroll" tabindex="0" aria-label="Call trace messages; scroll horizontally if needed">
        <table>
          <caption class="sr-only">SIP messages for Call-ID ${escapeHtml(trace.callId)}</caption>
          <thead><tr><th scope="col">Time</th><th scope="col">Direction</th><th scope="col">Method / response</th><th scope="col">Call-ID</th><th scope="col">From</th><th scope="col">To</th><th scope="col">Event</th></tr></thead>
          <tbody>${trace.messages.map((message) => `<tr>
            <td class="mono">${escapeHtml(message.time)}</td>
            <td><span class="direction-pill ${message.direction === "OUT" ? "direction-out" : ""}">${escapeHtml(message.direction)}</span></td>
            <td class="mono">${escapeHtml(message.method)}<br />${escapeHtml(message.response)}</td>
            <td class="mono">${escapeHtml(message.callId || trace.callId)}</td>
            <td class="mono">${escapeHtml(message.from)}</td>
            <td class="mono">${escapeHtml(message.to)}</td>
            <td>${escapeHtml(message.detail)}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  function renderTraces() {
    const traces = matchingTraces();
    if (!traces.some((trace) => trace.callId === selectedTraceId)) {
      selectedTraceId = null;
    }
    elements.traceResults.innerHTML = traces.length
      ? traces.map((trace) => `<tr class="${trace.callId === selectedTraceId ? "trace-row-selected" : ""}">
          <td><button class="button-link trace-call-id" type="button" data-trace-id="${escapeHtml(trace.callId)}" aria-label="Open trace ${escapeHtml(trace.callId)}">${escapeHtml(trace.callId)}</button><small class="secondary-cell">${escapeHtml(trace.from)} → ${escapeHtml(trace.to)}</small></td>
          <td class="mono">${escapeHtml(trace.startedAt)}</td>
          <td>${statusBadge(trace.outcome === "200 OK" ? "Approved" : "Rejected", trace.outcome)}</td>
        </tr>`).join("")
      : `<tr class="row-empty"><td colspan="3">No fixture traces match this Call-ID.</td></tr>`;

    elements.traceListCount.textContent = `${traces.length} ${traces.length === 1 ? "trace" : "traces"}`;
    elements.traceResultSummary.textContent = traceQuery
      ? `${traces.length} fixture ${traces.length === 1 ? "trace" : "traces"} matching “${elements.traceSearch.value.trim()}”.`
      : `${traces.length} fixture traces available. Search by full or partial Call-ID.`;
    renderTraceDetail(traces.find((trace) => trace.callId === selectedTraceId) || null);
  }

  function renderAll() {
    renderRules();
    renderChangeOrders();
    if (isPreview) renderTraces();
  }

  function showView(name) {
    if (!viewCopy[name]) return;
    document.querySelectorAll("[data-nav-target]").forEach((button) => {
      const current = button.dataset.navTarget === name;
      button.classList.toggle("is-current", current);
      button.setAttribute("aria-current", current ? "page" : "false");
    });
    document.querySelectorAll("[data-view-section]").forEach((section) => {
      const current = section.dataset.viewSection === name;
      section.hidden = !current;
      section.classList.toggle("is-active", current);
      if (current) {
        section.classList.remove("view-enter");
        void section.offsetWidth;
        section.classList.add("view-enter");
      }
    });
    elements.pageTitle.textContent = viewCopy[name].title;
    elements.pageDescription.textContent = viewCopy[name].description;
    elements.createRuleButton.hidden = !isPreview || name !== "rules";
    document.title = `${viewCopy[name].title} | AS Operations`;
  }

  function showToast(message, isError = false) {
    const toast = document.createElement("div");
    toast.className = `toast${isError ? " toast-error" : ""}`;
    toast.textContent = message;
    elements.toastRegion.replaceChildren(toast);
    window.setTimeout(() => {
      if (toast.isConnected) toast.remove();
    }, 4200);
  }

  function setLiveStatus(message, { error = false, retry = false } = {}) {
    elements.liveStatus.hidden = isPreview || !message;
    elements.liveStatus.classList.toggle("is-error", error);
    elements.liveStatusMessage.textContent = message;
    elements.reloadDataButton.hidden = !retry;
  }

  function configureMode() {
    document.querySelectorAll("[data-preview-only]").forEach((element) => {
      element.hidden = !isPreview;
    });
    document.querySelectorAll("[data-live-only]").forEach((element) => {
      element.hidden = isPreview;
    });
    elements.previewBanner.hidden = !isPreview;
    elements.loginButton.hidden = isPreview;
    elements.logoutButton.hidden = true;
    elements.createRuleButton.hidden = !isPreview;
    elements.liveStatus.hidden = true;
    elements.environmentLabel.textContent = isPreview ? "Local preview" : "Live console";
    elements.identityUser.textContent = isPreview ? "Not connected" : "Checking session";
    elements.identityRoles.textContent = isPreview ? "Read-only placeholder" : "Live session";
    elements.rulesDescription.textContent = isPreview
      ? "Approval updates local preview state only; no routing backend is connected. New or edited values wait for a change-order decision."
      : "Managed rules reflect the current API records. Change-order approval does not activate a rule until distribution is applied.";
    elements.ordersDescription.textContent = isPreview
      ? "Review proposed rule changes. Local approval only updates this preview."
      : "Track change-order state through approval and distribution. Approval alone does not activate a rule.";
    elements.tracesDescription.textContent = isPreview
      ? "Search fixture traces by Call-ID and inspect their message sequence."
      : "Live Call-ID trace search is not available in this integration.";
    elements.operationsDescription.textContent = isPreview
      ? "A fixed fixture snapshot for layout preview; no telemetry is connected."
      : "Live service telemetry is not available in this integration.";
    elements.ruleRevisionHeading.textContent = isPreview ? "Version / updated" : "Revision";
    if (!isPreview) {
      elements.pageDescription.textContent = viewCopy.rules.description;
      elements.ruleTotalLabel.textContent = "records";
      elements.rulePendingLabel.textContent = "draft / submitted";
      elements.ordersPendingLabel.textContent = "draft / submitted";
      elements.orderCreatedHeading.textContent = "Created";
      elements.orderStateHeading.textContent = "State";
      elements.ruleStateFilter.options[3].textContent = "Draft / submitted";
      elements.orderStateFilter.replaceChildren(
        new Option("All states", "all"),
        ...["draft", "submitted", "approved", "distributing", "applied", "rejected", "rolled_back"]
          .map((status) => new Option(liveStatusLabel(status), status)),
      );
    }
  }

  function formatTimestamp(timestamp) {
    if (typeof timestamp !== "number" || !Number.isFinite(timestamp)) return "Time unavailable";
    return new Date(timestamp * 1000).toISOString().replace("T", " ").replace(".000Z", " UTC");
  }

  function mapManagedRule(item) {
    const record = item.record?.rule;
    if (!record) {
      return {
        id: `tombstone-revision-${item.revision}`,
        name: "Deleted rule (tombstone)",
        matchField: "—",
        matchType: "—",
        matchValue: "—",
        target: "—",
        targetDetail: "—",
        enabled: false,
        revision: item.revision,
        version: String(item.revision),
        updatedAt: "",
        isTombstone: true,
      };
    }

    return mapRuleRecord(record, item.revision);
  }

  function mapRuleRecord(record, revision) {
    const targets = {
      translation: "Translation",
      "anti-fraud": "Anti-fraud",
      routing: "Routing",
      block: "Block",
      default: "Default",
    };
    return {
      id: record.rule_id,
      name: record.name,
      matchField: record.match_field === "calling" ? "Calling party" : "Called party",
      matchType: record.match_mode === "regex" ? "Regex" : "Prefix",
      matchValue: record.match_value,
      target: targets[record.target_service] || record.target_service,
      targetDetail: record.target_detail || "—",
      enabled: record.enabled,
      revision,
      version: String(revision),
      updatedAt: "",
      isTombstone: false,
    };
  }

  function mapChangeOrder(item) {
    const order = item.record?.order;
    const change = order?.managed_rule_change;
    const ruleId = change?.rule_id || "—";
    const proposedRule = change?.proposed_rule;
    const currentRule = state.rules.find((rule) => rule.id === ruleId);
    return {
      id: order?.change_id || "Unknown change order",
      revision: item.revision,
      action: change?.action ? `${change.action.charAt(0).toUpperCase()}${change.action.slice(1)}` : "Bundle",
      ruleId,
      ruleName: proposedRule?.name || currentRule?.name || "Configuration bundle",
      payload: proposedRule ? mapRuleRecord(proposedRule, "—") : null,
      requestedBy: order?.created_by || "Unknown",
      createdBy: order?.created_by || null,
      createdAt: formatTimestamp(order?.created_at),
      status: order?.state || "unknown",
      record: order || null,
    };
  }

  async function apiRequest(path, { method = "GET", body, csrf = false } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (csrf) {
      const token = document.cookie.split(";").map((cookie) => cookie.trim())
        .find((cookie) => cookie.startsWith("__Host-as_console_csrf="))
        ?.slice("__Host-as_console_csrf=".length);
      if (!token) throw new Error("CSRF cookie is unavailable; sign in again.");
      headers["X-CSRF-Token"] = decodeURIComponent(token);
    }
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: "same-origin",
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  function applySession(session) {
    authenticated = true;
    sessionUserId = session.user_id || null;
    sessionRoles = Array.isArray(session.roles) ? session.roles : [];
    elements.identityUser.textContent = sessionUserId || "Signed in";
    elements.identityRoles.textContent = Array.isArray(session.roles) && session.roles.length
      ? session.roles.join(" · ")
      : "No roles assigned";
    elements.loginButton.hidden = true;
    elements.logoutButton.hidden = false;
    elements.createRuleButton.hidden = true;
  }

  function clearSession() {
    authenticated = false;
    sessionUserId = null;
    sessionRoles = [];
    elements.identityUser.textContent = "Not signed in";
    elements.identityRoles.textContent = "Sign in to read configuration";
    elements.loginButton.hidden = false;
    elements.logoutButton.hidden = true;
    state.rules = [];
    state.changeOrders = [];
  }

  async function loadLiveData() {
    if (!authenticated) return;
    state.rules = [];
    state.changeOrders = [];
    liveData.rules = "loading";
    liveData.orders = "loading";
    setLiveStatus("Loading managed rules and change orders…");
    renderAll();

    const results = await Promise.allSettled([
      apiRequest("/managed-rules"),
      apiRequest("/change-orders"),
    ]);
    const expired = results.some((result) => result.status === "rejected" && result.reason.status === 401);
    if (expired) {
      clearSession();
      liveData.rules = "unauthenticated";
      liveData.orders = "unauthenticated";
      setLiveStatus("Your session expired. Sign in again.", { error: true });
      renderAll();
      return;
    }

    const errors = [];
    if (results[0].status === "fulfilled" && Array.isArray(results[0].value)) {
      state.rules = results[0].value.map(mapManagedRule);
      liveData.rules = "ready";
    } else {
      liveData.rules = "error";
      errors.push(`managed rules (${results[0].status === "rejected" ? results[0].reason.message : "invalid response"})`);
    }
    if (results[1].status === "fulfilled" && Array.isArray(results[1].value)) {
      state.changeOrders = results[1].value.map(mapChangeOrder);
      liveData.orders = "ready";
    } else {
      liveData.orders = "error";
      errors.push(`change orders (${results[1].status === "rejected" ? results[1].reason.message : "invalid response"})`);
    }
    renderAll();
    setLiveStatus(errors.length ? `Could not load ${errors.join("; ")}.` : "Live configuration loaded.", {
      error: errors.length > 0,
      retry: errors.length > 0,
    });
  }

  async function restoreSession() {
    setLiveStatus("Checking operator session…");
    try {
      const session = await apiRequest("/auth/session");
      applySession(session);
      await loadLiveData();
    } catch (error) {
      clearSession();
      liveData.rules = error.status === 401 || error.status === 403 ? "unauthenticated" : "error";
      liveData.orders = liveData.rules;
      renderAll();
      if (error.status === 401 || error.status === 403) {
        setLiveStatus("Sign in to load managed rules and change orders.");
      } else {
        setLiveStatus("Could not restore the operator session. Check the live API connection and retry.", { error: true, retry: true });
      }
    }
  }

  async function submitLogin(event) {
    event.preventDefault();
    if (isPreview) return;
    elements.loginError.hidden = true;
    elements.loginError.textContent = "";
    if (window.location.protocol !== "https:") {
      elements.loginError.textContent = "HTTPS is required for sign in.";
      elements.loginError.hidden = false;
      return;
    }
    elements.loginSubmit.disabled = true;
    try {
      await apiRequest("/auth/login", {
        method: "POST",
        body: { user_id: elements.loginUserId.value, password: elements.loginPassword.value },
      });
      const session = await apiRequest("/auth/session");
      applySession(session);
      elements.loginDialog.close();
      await loadLiveData();
    } catch (error) {
      elements.loginError.textContent = error.status === 401
        ? "Sign in failed. Check the user ID and password."
        : "Sign in failed. Check the HTTPS API connection and try again.";
      elements.loginError.hidden = false;
    } finally {
      elements.loginPassword.value = "";
      elements.loginSubmit.disabled = false;
    }
  }

  async function logout() {
    try {
      await apiRequest("/auth/logout", { method: "POST", csrf: true });
      clearSession();
      liveData.rules = "unauthenticated";
      liveData.orders = "unauthenticated";
      setLiveStatus("Signed out. Sign in to load configuration.");
      renderAll();
    } catch {
      setLiveStatus("Sign out failed. The session may still be active; retry.", { error: true });
    }
  }

  function localTimestamp() {
    return `${new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date())} local`;
  }

  function nextVersion(version) {
    const number = Number(String(version).replace(/^v/, ""));
    return Number.isFinite(number) ? `v${String(number + 1).padStart(2, "0")}` : version;
  }

  function queueChange(action, ruleId, ruleName, payload, before) {
    if (pendingOrderFor(ruleId)) {
      showToast("This rule already has a pending change order.", true);
      return null;
    }
    const order = {
      id: `CO-${nextOrderNumber++}`,
      action,
      ruleId,
      ruleName,
      requestedBy: "Preview session",
      submittedAt: `${localTimestamp()} · this tab`,
      status: "Pending",
      before: copyRule(before),
      payload: copyRule(payload),
      reason: "",
    };
    state.changeOrders.unshift(order);
    renderAll();
    showToast(`${order.id} queued locally. Review it in Change orders.`);
    return order;
  }

  function openRuleDialog(rule = null) {
    editingRuleId = rule?.id || null;
    elements.ruleForm.reset();
    elements.ruleDialogTitle.textContent = rule ? `Edit ${rule.id}` : "New rule";
    elements.ruleName.value = rule?.name || "";
    document.querySelector("#rule-match-field").value = rule?.matchField || "Called party";
    elements.ruleMatchType.value = rule?.matchType || "Prefix";
    elements.ruleMatchValue.value = rule?.matchValue || "";
    document.querySelector("#rule-target").value = rule?.target || "Translation";
    document.querySelector("#rule-target-detail").value = rule?.targetDetail || "";
    document.querySelector("#rule-enabled").checked = rule ? rule.enabled : true;
    elements.ruleDialog.showModal();
    elements.ruleName.focus();
  }

  function ruleDetailMarkup(rule) {
    if (!rule) return `<p>No current rule. This request will create a new rule.</p>`;
    return `<dl>
      <dt>Name</dt><dd>${escapeHtml(rule.name)}</dd>
      <dt>Rule ID</dt><dd class="mono">${escapeHtml(rule.id)}</dd>
      <dt>Match</dt><dd>${escapeHtml(formatMatch(rule))}: <span class="mono">${escapeHtml(rule.matchValue)}</span></dd>
      <dt>Service</dt><dd>${escapeHtml(rule.target)} · ${escapeHtml(rule.targetDetail)}</dd>
      <dt>Enabled</dt><dd>${rule.enabled ? "Yes" : "No"}</dd>
    </dl>`;
  }

  function openChangeOrder(orderId) {
    const order = state.changeOrders.find((item) => item.id === orderId);
    if (!order) return;
    selectedOrderId = order.id;
    if (!isPreview) {
      const storedOrder = order.record;
      const change = storedOrder?.managed_rule_change;
      const currentRule = state.rules.find((rule) => rule.id === change?.rule_id) || null;
      const proposedRule = change?.proposed_rule
        ? mapRuleRecord(change.proposed_rule, "—")
        : null;
      const action = liveOrderAction(order);
      elements.reviewTitle.textContent = `${order.id} · ${order.action} rule`;
      elements.reviewMeta.innerHTML = `<span>Rule<strong>${escapeHtml(order.ruleName)} (${escapeHtml(order.ruleId)})</strong></span>
        <span>State<strong>${escapeHtml(liveStatusLabel(order.status))}</strong></span>
        <span>Created by<strong>${escapeHtml(order.createdBy || "Unavailable")}</strong></span>
        <span>Created<strong>${escapeHtml(order.createdAt)}</strong></span>
        <span>Revision<strong>${escapeHtml(order.revision ?? "Unavailable")}</strong></span>`;
      elements.reviewCurrent.innerHTML = currentRule
        ? ruleDetailMarkup(currentRule)
        : `<p>Current managed rule unavailable.</p>`;
      elements.reviewProposed.innerHTML = proposedRule
        ? ruleDetailMarkup(proposedRule)
        : `<p>Proposed rule unavailable in this change order.</p>`;
      const audit = storedOrder?.audit;
      const auditText = audit === undefined || audit === null
        ? "Unavailable"
        : typeof audit === "string" ? audit : JSON.stringify(audit);
      elements.reviewStatus.textContent = `${liveStatusLabel(order.status)} · Audit: ${auditText}. Approval does not mean the change has been applied.`;
      elements.reviewActions.hidden = action !== "submit" && action !== "review";
      const approveButton = document.querySelector("#approve-change");
      approveButton.textContent = action === "submit" ? "Submit change" : "Approve change";
      document.querySelector("#show-reject-form").hidden = action !== "review";
      elements.rejectForm.hidden = true;
      elements.rejectForm.reset();
      elements.reviewDialog.showModal();
      return;
    }
    elements.reviewTitle.textContent = `${order.id} · ${order.action} rule`;
    elements.reviewMeta.innerHTML = `<span>Rule<strong>${escapeHtml(order.ruleName)} (${escapeHtml(order.ruleId)})</strong></span>
      <span>Requested by<strong>${escapeHtml(order.requestedBy)}</strong></span>
      <span>Submitted<strong>${escapeHtml(order.submittedAt)}</strong></span>`;
    elements.reviewCurrent.innerHTML = ruleDetailMarkup(order.before);
    elements.reviewProposed.innerHTML = order.action === "Delete"
      ? `<p>Rule <span class="mono">${escapeHtml(order.ruleId)}</span> will be removed if this request is approved.</p>`
      : ruleDetailMarkup(order.payload);
    elements.reviewStatus.textContent = order.status === "Pending"
      ? "Awaiting decision in this local preview."
      : `${order.status}${order.decidedAt ? ` · ${order.decidedAt}` : ""}${order.reason ? ` · Reason: ${order.reason}` : ""}`;
    elements.reviewActions.hidden = order.status !== "Pending";
    elements.rejectForm.hidden = true;
    elements.rejectForm.reset();
    elements.reviewDialog.showModal();
  }

  function applyApprovedChange(order) {
    const existingIndex = state.rules.findIndex((rule) => rule.id === order.ruleId);
    const existing = existingIndex >= 0 ? state.rules[existingIndex] : null;
    if (order.action === "Create" && !existing) {
      state.rules.push({ ...order.payload, version: "v01", updatedAt: `${localTimestamp()} · preview` });
    } else if (order.action === "Update" && existing) {
      state.rules[existingIndex] = { ...order.payload, version: nextVersion(existing.version), updatedAt: `${localTimestamp()} · preview` };
    } else if ((order.action === "Enable" || order.action === "Disable") && existing) {
      state.rules[existingIndex] = {
        ...existing,
        enabled: order.action === "Enable",
        version: nextVersion(existing.version),
        updatedAt: `${localTimestamp()} · preview`,
      };
    } else if (order.action === "Delete" && existing) {
      state.rules.splice(existingIndex, 1);
    }
    order.status = "Approved";
    order.decidedAt = `${localTimestamp()} · local`;
    order.decidedBy = "Preview action";
  }

  async function performLiveOrderAction(action, reason) {
    const order = state.changeOrders.find((item) => item.id === selectedOrderId);
    if (!order) return;
    const actionButton = document.querySelector("#approve-change");
    const rejectButton = elements.rejectForm.querySelector('[type="submit"]');
    actionButton.disabled = true;
    rejectButton.disabled = true;
    elements.reviewStatus.textContent = "Sending change-order decision…";
    const endpoint = action === "submit" ? "submit" : action === "approve" ? "approve" : "reject";
    try {
      await apiRequest(`/change-orders/${encodeURIComponent(order.id)}/${endpoint}`, {
        method: "POST",
        ...(action === "reject" ? { body: { reason } } : {}),
        csrf: true,
      });
      elements.reviewDialog.close();
      await loadLiveData();
      const refreshedOrder = state.changeOrders.find((item) => item.id === order.id);
      if (liveData.orders === "ready" && refreshedOrder) {
        showToast(`${order.id} is now ${liveStatusLabel(refreshedOrder.status)}.`);
      } else if (liveData.orders === "ready") {
        showToast(`${order.id} was updated and is no longer in the returned change-order list.`);
      } else {
        showToast(`${order.id} action succeeded, but its resulting state could not be reloaded.`, true);
      }
    } catch (error) {
      if (error.status === 401) {
        clearSession();
        liveData.rules = "unauthenticated";
        liveData.orders = "unauthenticated";
        renderAll();
        elements.reviewActions.hidden = true;
        elements.rejectForm.hidden = true;
        elements.reviewStatus.textContent = "Your session expired. Sign in again; the change order was not confirmed.";
      } else if (error.status === 403) {
        elements.reviewStatus.textContent = "This action is not permitted for your session. The change order was not changed.";
      } else if (error.status === 409) {
        elements.reviewStatus.textContent = "The change order state has changed. Reload the live data before trying again.";
      } else if (error.status >= 500) {
        elements.reviewStatus.textContent = "The service could not complete this action. The change order was not confirmed.";
      } else {
        elements.reviewStatus.textContent = "The request failed. The change order was not confirmed.";
      }
    } finally {
      actionButton.disabled = false;
      rejectButton.disabled = false;
    }
  }

  document.querySelectorAll("[data-nav-target]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.navTarget));
  });

  elements.loginButton.addEventListener("click", () => {
    if (isPreview) return;
    elements.loginError.hidden = true;
    elements.loginDialog.showModal();
    elements.loginUserId.focus();
  });
  elements.logoutButton.addEventListener("click", logout);
  elements.loginForm.addEventListener("submit", submitLogin);
  elements.reloadDataButton.addEventListener("click", () => {
    if (authenticated) loadLiveData();
    else restoreSession();
  });

  elements.createRuleButton.addEventListener("click", () => {
    if (isPreview) openRuleDialog();
  });
  elements.ruleSearch.addEventListener("input", renderRules);
  elements.ruleStateFilter.addEventListener("change", renderRules);
  elements.orderSearch.addEventListener("input", renderChangeOrders);
  elements.orderStateFilter.addEventListener("change", renderChangeOrders);

  elements.rulesTable.addEventListener("click", (event) => {
    if (!isPreview) return;
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.openOrder) {
      openChangeOrder(button.dataset.openOrder);
      return;
    }
    const rule = state.rules.find((item) => item.id === button.dataset.ruleId);
    if (!rule) return;
    if (button.dataset.ruleAction === "edit") {
      openRuleDialog(rule);
    } else if (button.dataset.ruleAction === "toggle") {
      const action = rule.enabled ? "Disable" : "Enable";
      queueChange(action, rule.id, rule.name, { ...rule, enabled: !rule.enabled }, rule);
    } else if (button.dataset.ruleAction === "delete") {
      const confirmed = window.confirm(`Queue a local deletion request for ${rule.id} · ${rule.name}?`);
      if (confirmed) queueChange("Delete", rule.id, rule.name, null, rule);
    }
  });

  elements.ordersTable.addEventListener("click", (event) => {
    if (!isPreview) {
      const button = event.target.closest("[data-open-order]");
      if (button) openChangeOrder(button.dataset.openOrder);
      return;
    }
    if (!isPreview) return;
    const button = event.target.closest("[data-open-order]");
    if (button) openChangeOrder(button.dataset.openOrder);
  });

  elements.ruleForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!isPreview) return;
    const name = elements.ruleName.value.trim();
    const matchValue = elements.ruleMatchValue.value.trim();
    const targetDetail = elements.ruleTargetDetail.value.trim();
    elements.ruleName.setCustomValidity(name ? "" : "Enter a rule name.");
    elements.ruleMatchValue.setCustomValidity(matchValue ? "" : "Enter a match value.");
    elements.ruleTargetDetail.setCustomValidity(targetDetail ? "" : "Enter target detail.");
    if (!elements.ruleForm.reportValidity()) return;
    if (elements.ruleMatchType.value === "Regex") {
      try {
        new RegExp(matchValue);
      } catch {
        elements.ruleMatchValue.setCustomValidity("Enter a valid regular expression.");
        elements.ruleMatchValue.reportValidity();
        return;
      }
    }
    const existing = editingRuleId ? state.rules.find((rule) => rule.id === editingRuleId) : null;
    if (existing && pendingOrderFor(existing.id)) {
      showToast("This rule already has a pending change order.", true);
      elements.ruleDialog.close();
      return;
    }
    const formData = new FormData(elements.ruleForm);
    const ruleId = existing?.id || `R-${nextRuleNumber++}`;
    const draft = {
      id: ruleId,
      name,
      matchField: String(formData.get("matchField")),
      matchType: String(formData.get("matchType")),
      matchValue,
      target: String(formData.get("target")),
      targetDetail,
      enabled: formData.get("enabled") === "on",
      version: existing?.version || "v01",
      updatedAt: existing?.updatedAt || "Preview session",
    };
    const order = queueChange(existing ? "Update" : "Create", ruleId, draft.name, draft, existing);
    if (order) elements.ruleDialog.close();
  });

  elements.ruleName.addEventListener("input", () => elements.ruleName.setCustomValidity(""));
  elements.ruleMatchValue.addEventListener("input", () => elements.ruleMatchValue.setCustomValidity(""));
  elements.ruleMatchType.addEventListener("change", () => elements.ruleMatchValue.setCustomValidity(""));
  elements.ruleTargetDetail.addEventListener("input", () => elements.ruleTargetDetail.setCustomValidity(""));
  elements.ruleForm.addEventListener("reset", () => {
    [elements.ruleName, elements.ruleMatchValue, elements.ruleTargetDetail].forEach((field) => {
      field.setCustomValidity("");
    });
  });

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => button.closest("dialog").close());
  });

  document.querySelector("#approve-change").addEventListener("click", () => {
    if (!isPreview) {
      const order = state.changeOrders.find((item) => item.id === selectedOrderId);
      const action = order && liveOrderAction(order);
      if (action === "submit") performLiveOrderAction("submit");
      else if (action === "review") performLiveOrderAction("approve");
      return;
    }
    const order = state.changeOrders.find((item) => item.id === selectedOrderId);
    if (!order || order.status !== "Pending") return;
    applyApprovedChange(order);
    elements.reviewDialog.close();
    renderAll();
    elements.pageTitle.focus();
    showToast(`${order.id} approved in local preview. No backend or audit record was written.`);
  });

  document.querySelector("#show-reject-form").addEventListener("click", () => {
    elements.rejectForm.hidden = false;
    elements.rejectReason.focus();
  });

  document.querySelector("#cancel-rejection").addEventListener("click", () => {
    elements.rejectForm.hidden = true;
    elements.rejectReason.setCustomValidity("");
    document.querySelector("#show-reject-form").focus();
  });

  elements.rejectReason.addEventListener("input", () => elements.rejectReason.setCustomValidity(""));
  elements.rejectForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const reason = elements.rejectReason.value.trim();
    if (!reason) {
      elements.rejectReason.setCustomValidity("Enter a rejection reason.");
      elements.rejectReason.reportValidity();
      return;
    }
    const order = state.changeOrders.find((item) => item.id === selectedOrderId);
    if (!order) return;
    if (!isPreview) {
      if (liveOrderAction(order) !== "review") return;
      performLiveOrderAction("reject", reason);
      return;
    }
    if (order.status !== "Pending") return;
    order.status = "Rejected";
    order.reason = reason;
    order.decidedAt = `${localTimestamp()} · local`;
    order.decidedBy = "Preview action";
    elements.reviewDialog.close();
    renderAll();
    elements.pageTitle.focus();
    showToast(`${order.id} rejected in local preview. No audit record was written.`);
  });

  elements.traceSearch.addEventListener("input", () => {
    traceQuery = elements.traceSearch.value.trim().toLowerCase();
    renderTraces();
  });

  elements.traceSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    traceQuery = elements.traceSearch.value.trim().toLowerCase();
    const firstMatch = matchingTraces()[0];
    selectedTraceId = firstMatch?.callId || null;
    renderTraces();
  });

  document.querySelector("#clear-trace-search").addEventListener("click", () => {
    elements.traceSearch.value = "";
    traceQuery = "";
    selectedTraceId = state.traces[0]?.callId || null;
    renderTraces();
    elements.traceSearch.focus();
  });

  elements.traceResults.addEventListener("click", (event) => {
    const button = event.target.closest("[data-trace-id]");
    if (!button) return;
    selectedTraceId = button.dataset.traceId;
    renderTraces();
    const selectedButton = Array.from(elements.traceResults.querySelectorAll("[data-trace-id]"))
      .find((resultButton) => resultButton.dataset.traceId === selectedTraceId);
    selectedButton?.focus();
  });

  configureMode();
  renderAll();
  if (!isPreview) restoreSession();
})();