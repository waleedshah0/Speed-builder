"""
main.py  -  POC: Semantic Field Mapper
========================================
POST /api/submit-entry

Flow:
  1. Accept any JSON payload from the client.
  2. Use OpenAI to semantically map client fields to our canonical schema.
  3. Validate that all required fields are present after mapping.
  4. Persist the record to the `user` table in PostgreSQL.
  5. Return a detailed JSON response.
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import Any, Dict

from database import engine, get_db, Base
from models import User
from schemas import UserResponse
from mapper import map_fields_with_ai, validate_mapped_payload

# Bootstrap
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Semantic Field Mapper POC",
    description=(
        "Accepts arbitrary client payloads, uses AI to map fields "
        "to the canonical schema, then stores the result in PostgreSQL."
    ),
    version="1.0.0",
)


# Endpoint

@app.post("/api/submit-entry", response_model=UserResponse)
def submit_entry(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Main entry-point.

    The client may send field names that differ from our schema, e.g.:
      Full_Name   -> Name
      Phone_No    -> Phone_Number
      Passport_No -> National_ID
      DOB         -> Date_of_Birth  (value also reformatted)

    OpenAI decides the mapping based on semantic meaning.
    Fields with a genuinely different meaning are rejected.
    """
    str_payload: Dict[str, str] = {k: str(v) for k, v in payload.items()}

    try:
        mapped, unmatched = map_fields_with_ai(str_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI mapping failed: {exc}",
        )

    is_valid, missing = validate_mapped_payload(mapped)
    if not is_valid:
        return JSONResponse(
            status_code=422,
            content=UserResponse(
                success=False,
                message=(
                    f"Mapping incomplete. Missing required fields after AI mapping: "
                    f"{missing}. "
                    f"These client fields could not be matched: {list(unmatched.keys())}"
                ),
                original_payload=payload,
                mapped_payload=mapped,
                unmatched_fields=unmatched,
            ).model_dump(),
        )

    existing_email = (
        db.query(User).filter(User.Email == mapped["Email"]).first()
    )
    if existing_email:
        raise HTTPException(
            status_code=409,
            detail=f"A user with Email '{mapped['Email']}' already exists.",
        )

    existing_id = (
        db.query(User).filter(User.National_ID == mapped["National_ID"]).first()
    )
    if existing_id:
        raise HTTPException(
            status_code=409,
            detail=f"A user with National_ID '{mapped['National_ID']}' already exists.",
        )

    new_user = User(
        Name          = mapped["Name"],
        Email         = mapped["Email"],
        Phone_Number  = mapped["Phone_Number"],
        Address       = mapped["Address"],
        National_ID   = mapped["National_ID"],
        Date_of_Birth = mapped["Date_of_Birth"],
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return UserResponse(
        success=True,
        message="Entry successfully mapped and saved.",
        original_payload=payload,
        mapped_payload=mapped,
        saved_record=new_user.to_dict(),
        unmatched_fields=unmatched if unmatched else None,
    )


@app.get("/", response_class=HTMLResponse)
def frontend():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Semantic Field Mapper</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Geist:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-0: #0a0a0b;
      --bg-1: #111114;
      --bg-2: #16161a;
      --bg-3: #1c1c22;
      --border: #26262e;
      --border-strong: #34343f;
      --text-0: #f5f5f7;
      --text-1: #a8a8b3;
      --text-2: #6c6c78;
      --accent: #d4ff4d;
      --accent-dim: rgba(212, 255, 77, 0.12);
      --danger: #ff6b6b;
      --success: #4ade80;
      --warn: #fbbf24;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html, body {
      background: var(--bg-0);
      color: var(--text-0);
      font-family: 'Geist', system-ui, sans-serif;
      font-size: 15px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
    }

    body {
      background-image:
        radial-gradient(circle at 20% 0%, rgba(212, 255, 77, 0.04), transparent 50%),
        radial-gradient(circle at 80% 100%, rgba(99, 102, 241, 0.03), transparent 50%);
      background-attachment: fixed;
    }

    .grain {
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.035;
      z-index: 1;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' /%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' /%3E%3C/svg%3E");
    }

    .container {
      max-width: 1240px;
      margin: 0 auto;
      padding: 32px 28px 80px;
      position: relative;
      z-index: 2;
    }

    /* Header */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 28px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 48px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      letter-spacing: 0.02em;
      color: var(--text-1);
    }

    .logo-mark {
      width: 28px;
      height: 28px;
      background: var(--accent);
      border-radius: 6px;
      display: grid;
      place-items: center;
      color: #0a0a0b;
      font-weight: 700;
      font-size: 14px;
      box-shadow: 0 0 24px var(--accent-dim);
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--text-1);
      padding: 6px 12px;
      background: var(--bg-2);
      border: 1px solid var(--border);
      border-radius: 100px;
    }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }

    /* Hero */
    .hero {
      margin-bottom: 56px;
      max-width: 720px;
      animation: rise 0.7s cubic-bezier(0.16, 1, 0.3, 1);
    }

    @keyframes rise {
      from { opacity: 0; transform: translateY(16px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .eyebrow {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--accent);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 20px;
      display: inline-block;
    }

    h1 {
      font-family: 'Instrument Serif', serif;
      font-size: clamp(42px, 6vw, 64px);
      line-height: 1.05;
      font-weight: 400;
      letter-spacing: -0.02em;
      margin-bottom: 20px;
    }

    h1 em {
      font-style: italic;
      color: var(--accent);
    }

    .hero-sub {
      color: var(--text-1);
      font-size: 17px;
      line-height: 1.55;
      max-width: 580px;
    }

    /* Two-column layout */
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 28px;
      animation: rise 0.9s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both;
    }

    .panel {
      background: var(--bg-1);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      background: var(--bg-2);
    }

    .panel-title {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--text-1);
      letter-spacing: 0.04em;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .panel-title::before {
      content: '';
      width: 4px;
      height: 4px;
      background: var(--accent);
      border-radius: 50%;
    }

    .panel-meta {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--text-2);
    }

    .panel-body {
      padding: 8px;
      flex: 1;
      min-height: 320px;
    }

    /* Field rows */
    .field-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) auto;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 10px;
      transition: background 0.15s ease;
    }

    .field-row:hover {
      background: var(--bg-2);
    }

    .field-row input {
      width: 100%;
      padding: 11px 13px;
      background: var(--bg-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-0);
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      transition: all 0.15s ease;
    }

    .field-row input::placeholder {
      color: var(--text-2);
    }

    .field-row input:focus {
      outline: none;
      border-color: var(--accent);
      background: var(--bg-3);
      box-shadow: 0 0 0 3px var(--accent-dim);
    }

    .field-row input[name="fieldName"] {
      color: var(--accent);
      font-weight: 500;
    }

    .remove-btn {
      width: 38px;
      height: 38px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-2);
      cursor: pointer;
      display: grid;
      place-items: center;
      transition: all 0.15s ease;
      align-self: center;
    }

    .remove-btn:hover {
      border-color: var(--danger);
      color: var(--danger);
      background: rgba(255, 107, 107, 0.06);
    }

    .remove-btn svg {
      width: 14px;
      height: 14px;
    }

    /* Action bar */
    .actions {
      display: flex;
      gap: 10px;
      padding: 12px;
      border-top: 1px solid var(--border);
      background: var(--bg-2);
    }

    .btn {
      padding: 10px 18px;
      border: none;
      border-radius: 8px;
      font-family: 'Geist', sans-serif;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .btn-primary {
      background: var(--accent);
      color: #0a0a0b;
      flex: 1;
      justify-content: center;
    }

    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 24px rgba(212, 255, 77, 0.25);
    }

    .btn-primary:active {
      transform: translateY(0);
    }

    .btn-secondary {
      background: var(--bg-3);
      color: var(--text-0);
      border: 1px solid var(--border-strong);
    }

    .btn-secondary:hover {
      background: var(--border);
      border-color: var(--text-2);
    }

    .btn-ghost {
      background: transparent;
      color: var(--text-1);
      border: 1px solid var(--border);
    }

    .btn-ghost:hover {
      color: var(--text-0);
      border-color: var(--text-2);
    }

    /* Code panels */
    pre {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12.5px;
      line-height: 1.7;
      color: var(--text-0);
      padding: 20px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 320px;
      max-height: 560px;
    }

    pre::-webkit-scrollbar { width: 8px; height: 8px; }
    pre::-webkit-scrollbar-track { background: transparent; }
    pre::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
    pre::-webkit-scrollbar-thumb:hover { background: var(--text-2); }

    .empty-state {
      padding: 60px 20px;
      text-align: center;
      color: var(--text-2);
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
    }

    .empty-state-icon {
      width: 40px;
      height: 40px;
      margin: 0 auto 16px;
      opacity: 0.4;
    }

    /* Response panel takes full width below */
    .response-panel {
      grid-column: 1 / -1;
      margin-top: 4px;
    }

    /* Status badge inside response */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 100px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      font-weight: 500;
    }

    .badge-success { background: rgba(74, 222, 128, 0.1); color: var(--success); }
    .badge-error { background: rgba(255, 107, 107, 0.1); color: var(--danger); }
    .badge-idle { background: var(--bg-3); color: var(--text-2); }

    /* JSON syntax tinting */
    .json-key { color: var(--accent); }
    .json-string { color: #a5e88f; }
    .json-number { color: #fbbf24; }
    .json-bool { color: #60a5fa; }
    .json-null { color: var(--text-2); }
    .json-punct { color: var(--text-2); }

    /* Loading spinner */
    .spinner {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(10, 10, 11, 0.2);
      border-top-color: #0a0a0b;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    /* Footer hint */
    .footer-hint {
      margin-top: 32px;
      padding: 16px 20px;
      background: var(--bg-1);
      border: 1px dashed var(--border);
      border-radius: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--text-1);
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .footer-hint strong {
      color: var(--accent);
      font-weight: 500;
    }

    /* Responsive */
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      .field-row { grid-template-columns: 1fr; }
      .remove-btn { width: 100%; height: 36px; }
      h1 { font-size: 38px; }
    }

    /* Selection */
    ::selection { background: var(--accent); color: #0a0a0b; }
  </style>
</head>
<body>
  <div class="grain"></div>
  <div class="container">

    <header>
      <div class="brand">
        <div class="logo-mark">S</div>
        <span>semantic-mapper / v1.0.0</span>
      </div>
      <div class="status-pill">
        <span class="dot"></span>
        <span>API connected</span>
      </div>
    </header>

    <section class="hero">
      <span class="eyebrow">POST /api/submit-entry</span>
      <h1>Map any payload to your <em>canonical schema</em>.</h1>
      <p class="hero-sub">
        Send arbitrary field names from any client. Our AI layer reads the meaning, not the labels, and maps them to your database schema. Test it live below.
      </p>
    </section>

    <div class="grid">

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Request builder</div>
          <div class="panel-meta" id="field-count">0 fields</div>
        </div>
        <div class="panel-body">
          <form id="field-form">
            <div id="fields"></div>
          </form>
        </div>
        <div class="actions">
          <button type="button" class="btn btn-secondary" id="add-field">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Add field
          </button>
          <button type="button" class="btn btn-ghost" id="clear-fields">Clear</button>
          <button type="button" class="btn btn-primary" id="submit-btn">
            <span id="submit-label">Run mapping</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M13 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Payload preview</div>
          <div class="panel-meta">application/json</div>
        </div>
        <pre id="payload-preview"></pre>
      </div>

      <div class="panel response-panel">
        <div class="panel-header">
          <div class="panel-title">Response</div>
          <div id="response-status">
            <span class="badge badge-idle">awaiting request</span>
          </div>
        </div>
        <pre id="api-response"><div class="empty-state">
  <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
  No request sent yet. Build a payload and run the mapping.
</div></pre>
      </div>

    </div>

    <div class="footer-hint">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0; margin-top:1px; color: var(--accent);">
        <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
      </svg>
      <div>
        <strong>Tip.</strong> Try mismatched field names like <code>Full_Name</code>, <code>Phone_No</code>, <code>Passport_No</code>, <code>DOB</code>. The AI will resolve them to <code>Name</code>, <code>Phone_Number</code>, <code>National_ID</code>, and <code>Date_of_Birth</code>.
      </div>
    </div>

  </div>

  <script>
    const fieldsContainer = document.getElementById('fields');
    const preview = document.getElementById('payload-preview');
    const apiResponse = document.getElementById('api-response');
    const responseStatus = document.getElementById('response-status');
    const fieldCount = document.getElementById('field-count');
    const submitBtn = document.getElementById('submit-btn');
    const submitLabel = document.getElementById('submit-label');

    const exampleRows = [
      ['Full_Name', 'Waleed Ahmad'],
      ['Email', 'ABC@gmail.com'],
      ['Phone_No', '02020202'],
      ['Address', 'ABC street'],
      ['Passport_No', 'ABC1223BNBN'],
      ['DOB', '28-12-2002'],
    ];

    function createFieldRow(key = '', value = '') {
      const row = document.createElement('div');
      row.className = 'field-row';

      const keyInput = document.createElement('input');
      keyInput.type = 'text';
      keyInput.name = 'fieldName';
      keyInput.placeholder = 'field_name';
      keyInput.value = key;
      keyInput.addEventListener('input', updatePreview);

      const valueInput = document.createElement('input');
      valueInput.type = 'text';
      valueInput.name = 'fieldValue';
      valueInput.placeholder = 'value';
      valueInput.value = value;
      valueInput.addEventListener('input', updatePreview);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'remove-btn';
      removeBtn.title = 'Remove field';
      removeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>';
      removeBtn.addEventListener('click', () => {
        row.style.opacity = '0';
        row.style.transform = 'translateX(-8px)';
        row.style.transition = 'all 0.15s ease';
        setTimeout(() => { row.remove(); updatePreview(); }, 150);
      });

      row.append(keyInput, valueInput, removeBtn);
      fieldsContainer.appendChild(row);
      return row;
    }

    function getPayload() {
      const payload = {};
      let duplicate = false;
      fieldsContainer.querySelectorAll('.field-row').forEach(row => {
        const key = row.querySelector('input[name="fieldName"]').value.trim();
        const value = row.querySelector('input[name="fieldValue"]').value.trim();
        if (key) {
          if (Object.prototype.hasOwnProperty.call(payload, key)) duplicate = true;
          payload[key] = value;
        }
      });
      return { payload, duplicate };
    }

    function syntaxHighlight(json) {
      if (typeof json !== 'string') json = JSON.stringify(json, null, 2);
      json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return json.replace(
        /("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^\\\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g,
        function (match) {
          let cls = 'json-number';
          if (/^"/.test(match)) {
            cls = /:$/.test(match) ? 'json-key' : 'json-string';
          } else if (/true|false/.test(match)) {
            cls = 'json-bool';
          } else if (/null/.test(match)) {
            cls = 'json-null';
          }
          return '<span class="' + cls + '">' + match + '</span>';
        }
      );
    }

    function updatePreview() {
      const { payload } = getPayload();
      const keys = Object.keys(payload);
      fieldCount.textContent = keys.length + (keys.length === 1 ? ' field' : ' fields');
      if (keys.length === 0) {
        preview.innerHTML = '<div class="empty-state">Add a field to begin.</div>';
      } else {
        preview.innerHTML = syntaxHighlight(JSON.stringify(payload, null, 2));
      }
    }

    function setStatus(kind, text) {
      const map = { success: 'badge-success', error: 'badge-error', idle: 'badge-idle' };
      responseStatus.innerHTML = '<span class="badge ' + map[kind] + '">' + text + '</span>';
    }

    document.getElementById('add-field').addEventListener('click', () => {
      const row = createFieldRow();
      row.querySelector('input[name="fieldName"]').focus();
      updatePreview();
    });

    document.getElementById('clear-fields').addEventListener('click', () => {
      fieldsContainer.innerHTML = '';
      updatePreview();
    });

    document.getElementById('submit-btn').addEventListener('click', async () => {
      const { payload, duplicate } = getPayload();

      if (duplicate) {
        setStatus('error', 'validation error');
        apiResponse.innerHTML = '<div class="empty-state" style="color: var(--danger);">Duplicate field names are not allowed.</div>';
        return;
      }

      if (Object.keys(payload).length === 0) {
        setStatus('error', 'empty payload');
        apiResponse.innerHTML = '<div class="empty-state" style="color: var(--danger);">Add at least one field before submitting.</div>';
        return;
      }

      submitBtn.disabled = true;
      submitLabel.innerHTML = '<span class="spinner" style="display:inline-block; vertical-align:middle; margin-right:6px;"></span>Mapping...';
      setStatus('idle', 'running');
      apiResponse.innerHTML = '<div class="empty-state">Sending payload to /api/submit-entry...</div>';

      try {
        const response = await fetch('/api/submit-entry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (response.ok && data.success !== false) {
          setStatus('success', 'HTTP ' + response.status + ' / mapped');
        } else {
          setStatus('error', 'HTTP ' + response.status + ' / failed');
        }
        apiResponse.innerHTML = syntaxHighlight(JSON.stringify(data, null, 2));
      } catch (error) {
        setStatus('error', 'network error');
        apiResponse.innerHTML = '<div class="empty-state" style="color: var(--danger);">Request failed: ' + error + '</div>';
      } finally {
        submitBtn.disabled = false;
        submitLabel.textContent = 'Run mapping';
      }
    });

    exampleRows.forEach(([k, v]) => createFieldRow(k, v));
    updatePreview();
  </script>
</body>
</html>
"""


# Health check

@app.get("/health")
def health():
    return {"status": "ok"}