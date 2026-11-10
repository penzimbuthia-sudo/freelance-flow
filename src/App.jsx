import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { PayPalProvider, PayPalOneTimePaymentButton } from '@paypal/react-paypal-js/sdk-v6'
import './App.css'

const money = (cents) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100)
const dueDate = (value) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`))
const paymentTime = (value) => new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi' }).format(new Date(value))

async function api(path, options = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } })
  } catch {
    throw new Error('Cannot reach the server. Check that Flask is running, then try again.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok || !data) throw new Error(data?.error?.message || 'The server could not complete this request. Please try again.')
  return data
}
const post = (path, data = {}) => api(path, { method: 'POST', body: JSON.stringify(data) })

function Icon({ name, size = 20 }) {
  const paths = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    requests: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m9 5 7 7-7 7" />,
    paid: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
    pending: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    overdue: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v4m0 3v1" /></>,
    ai: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" /><path d="m20 2 1 3 3 1" /></>,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M15 8V3H3v13h5" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    link: <><path d="m10 13 4-4m-6 6-2 2a4 4 0 0 0 6 6l4-4m0-10 2-2a4 4 0 0 0-6-6l-4 4" transform="translate(0 -2)" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.requests}</svg>
}

function useResource(path) {
  const [state, setState] = useState({ data: null, error: '', loading: true })
  const sequence = useRef(0)
  const invalidate = useCallback(() => { sequence.current++ }, [])
  const reload = useCallback(async () => {
    const current = ++sequence.current
    setState((old) => ({ ...old, error: '', loading: true }))
    try {
      const data = await api(path)
      if (current === sequence.current) setState({ data, error: '', loading: false })
    } catch (error) {
      if (current === sequence.current) setState((old) => ({ ...old, error: error.message, loading: false }))
    }
  }, [path])
  useEffect(() => {
    reload()
    window.addEventListener('focus', reload)
    return () => { invalidate(); window.removeEventListener('focus', reload) }
  }, [reload, invalidate])
  return { ...state, reload }
}

function ErrorNotice({ message, retry }) {
  return <div className="notice error" role="alert"><span>{message}</span>{retry && <button className="text-button" onClick={retry}>Try again</button>}</div>
}

function Loading() { return <div className="loading" role="status">Loading saved records…</div> }

function Status({ value }) {
  return <span className={`status ${value}`}><Icon name={value} size={15} />{value === 'paid' ? 'Paid' : value === 'overdue' ? 'Overdue' : 'Pending'}</span>
}

function Brand() {
  return <span className="brand"><span className="brand-mark">f<span>f</span></span><span>Freelance<span className="brand-light"> Flow</span></span></span>
}

function Shell({ children }) {
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand-link" aria-label="Freelance Flow home"><Brand /></Link>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <nav aria-label="Main navigation">
        <NavLink to="/" end><Icon name="dashboard" />Dashboard</NavLink>
        <NavLink to="/requests"><Icon name="requests" />Payment requests</NavLink>
      </nav>
      <div className="sidebar-note"><span className="sandbox-dot" />Sandbox workspace<p>Made for a calmer payday.</p></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><span>AI PAYMENT COMPANION</span><span className="sandbox-label">PayPal sandbox · USD only</span></header>
      <main id="main" tabIndex="-1">{children}</main>
      <footer className="workspace-footer">Single local workspace · Fictional demo data only · Due dates use Africa/Nairobi (UTC+3)</footer>
    </div>
  </div>
}

function PageHeading({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="muted">{description}</p></div>{action}</div>
}

function NewButton() { return <Link className="button primary" to="/requests/new"><Icon name="plus" />New Payment Request</Link> }

function Empty({ filtered = false }) {
  return <div className="empty"><span className="empty-icon"><Icon name="requests" size={30} /></span><h3>{filtered ? 'No matching requests' : 'Your next payday starts here'}</h3><p>{filtered ? 'Try another client name or status filter.' : 'Create your first request, then share a sandbox payment link with your client.'}</p>{!filtered && <NewButton />}</div>
}

function RequestTable({ requests, filtered = false }) {
  if (!requests.length) return <Empty filtered={filtered} />
  return <div className="table-scroll"><table><thead><tr><th>Client / service</th><th>Amount</th><th>Due date</th><th>Status</th><th><span className="sr-only">Details</span></th></tr></thead><tbody>
    {requests.map((item) => <tr key={item.id}>
      <td><Link className="client-link" to={`/requests/${item.id}`}>{item.client_name}</Link><span className="service-preview">{item.service_description}</span></td>
      <td className="amount-cell">{money(item.amount_cents)}<small>USD</small></td><td className="date-cell">{dueDate(item.due_date)}</td>
      <td><Status value={item.status} /></td><td><Link className="icon-link" to={`/requests/${item.id}`} aria-label={`View request for ${item.client_name}`}><Icon name="arrow" /></Link></td>
    </tr>)}
  </tbody></table></div>
}

function Dashboard() {
  const { data, error, loading, reload } = useResource('/dashboard')
  return <>
    <PageHeading eyebrow="A LITTLE CLARITY, EVERY DAY" title="Your money, in view." description="Less chasing payments. More time for your work." action={<NewButton />} />
    {error && <ErrorNotice message={error} retry={reload} />}
    {loading && !data ? <Loading /> : data && <>
      <section className="stats" aria-label="Payment totals">
        {[['paid', 'Paid amount', data.paid_cents, 'Confirmed payments'], ['pending', 'Outstanding amount', data.outstanding_cents, 'All unpaid requests'], ['overdue', 'Overdue amount', data.overdue_cents, 'Included in outstanding']].map(([kind, label, amount, help]) => <article className={`card stat ${kind}`} key={kind}><div className="stat-label"><span>{label}</span><span className="stat-icon"><Icon name={kind} /></span></div><div className="stat-value">{money(amount)}</div><p>{help}</p></article>)}
      </section>
      <section className="card requests-card"><div className="card-heading"><div><h2>Recent requests</h2><p className="muted">{data.request_count} saved {data.request_count === 1 ? 'request' : 'requests'} in your workspace</p></div><Link className="text-link" to="/requests">View all <Icon name="arrow" size={16} /></Link></div><RequestTable requests={data.recent_requests} /></section>
      <div className="ai-note"><span className="ai-note-icon"><Icon name="ai" size={24} /></span><div><h3>A thoughtful nudge, not another task.</h3><p>Open a request to draft a short AI payment message. Review it, make it yours, and share it when you’re ready.</p></div></div>
    </>}
  </>
}

function Requests() {
  const { data, error, loading, reload } = useResource('/requests')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const requests = data?.requests.filter((item) => (filter === 'all' || item.status === filter) && `${item.client_name} ${item.service_description}`.toLowerCase().includes(search.toLowerCase())) || []
  return <>
    <PageHeading eyebrow="KEEP EVERY REQUEST IN SIGHT" title="Payment requests" description="The details, the status, and the next step. All in one place." action={<NewButton />} />
    <section className="card requests-card">
      <div className="filters"><div className="search-field"><Icon name="search" /><label className="sr-only" htmlFor="search">Search requests</label><input id="search" type="search" placeholder="Search client or service…" value={search} onChange={(event) => setSearch(event.target.value)} /></div><div className="filter-field"><label htmlFor="status-filter">Status</label><select id="status-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All statuses</option><option value="pending">Pending</option><option value="overdue">Overdue</option><option value="paid">Paid</option></select></div></div>
      {error && <ErrorNotice message={error} retry={reload} />}
      {loading && !data ? <Loading /> : data && <RequestTable requests={requests} filtered={!!search || filter !== 'all'} />}
    </section>
  </>
}

function NewRequest() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ client_name: '', service_description: '', amount: '', due_date: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value })
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const data = await post('/requests', form)
      navigate(`/requests/${data.request.id}`, { state: { created: true } })
    } catch (error) { setError(error.message); setBusy(false) }
  }
  return <>
    <Link className="back-link" to="/requests">← Payment requests</Link>
    <PageHeading eyebrow="ONE SIMPLE STEP" title="New payment request" description="Save the details first. Draft a message and share the payment link next." />
    <form className="card request-form" onSubmit={submit}>
      <h2>Request details</h2><p className="muted">All fields are required. Use fictional client information for this demo.</p>
      <div className="field"><label htmlFor="client_name">Client name</label><input id="client_name" name="client_name" value={form.client_name} onChange={change} required maxLength={120} placeholder="e.g. Alex Demo" autoComplete="off" /></div>
      <div className="field"><label htmlFor="service_description">Service description</label><textarea id="service_description" name="service_description" value={form.service_description} onChange={change} required maxLength={1000} rows={3} placeholder="What did you create or deliver?" /><small>This description appears on the client payment page.</small></div>
      <div className="form-grid"><div className="field"><label htmlFor="amount">Amount (USD)</label><input id="amount" name="amount" value={form.amount} onChange={change} inputMode="decimal" required pattern="[0-9]{1,7}(\.[0-9]{1,2})?" title="Enter a positive USD amount with up to two decimal places, e.g. 50.00" placeholder="250.00" /><small>$0.01–$999,999.99; up to two decimal places.</small></div><div className="field"><label htmlFor="due_date">Due date</label><input id="due_date" name="due_date" type="date" value={form.due_date} onChange={change} required min="0001-01-01" max="9999-12-31" /><small>Due through this date in Africa/Nairobi (UTC+3).</small></div></div>
      {error && <ErrorNotice message={error} />}
      <div className="form-actions"><Link className="button secondary" to="/requests">Cancel</Link><button className="button primary" disabled={busy} type="submit">{busy ? 'Saving request…' : 'Create payment request'}{!busy && <Icon name="arrow" size={17} />}</button></div>
    </form>
  </>
}

function CopyButton({ text, label = 'Copy', className = 'secondary' }) {
  const [feedback, setFeedback] = useState(null)
  async function copy() {
    try { await navigator.clipboard.writeText(text); setFeedback({ text, message: 'Copied to clipboard.' }) }
    catch { setFeedback({ text, message: 'Clipboard unavailable. Select the text and copy it manually.' }) }
  }
  return <div className="copy-control"><button className={`button ${className}`} onClick={copy} disabled={!text}><Icon name="copy" size={17} />{label}</button>{feedback?.text === text && <small className="copy-feedback" role="status">{feedback.message}</small>}</div>
}

function AIPanel({ item, guidance }) {
  const settings = useResource('/settings')
  const [nameDraft, setNameDraft] = useState(null)
  const [savingName, setSavingName] = useState(false)
  const [nameError, setNameError] = useState('')
  const [nameFeedback, setNameFeedback] = useState('')
  const [message, setMessage] = useState('')
  const [source, setSource] = useState('')
  const [draftStatus, setDraftStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const savedName = settings.data?.settings.freelancer_display_name || ''
  const nameDirty = nameDraft !== null && nameDraft !== savedName
  const staleDraft = !!message && draftStatus !== null && draftStatus !== item.status
  async function saveName(event) {
    event.preventDefault()
    if (savingName || busy) return
    setSavingName(true); setNameError(''); setNameFeedback('')
    try {
      const result = await api('/settings', { method: 'PUT', body: JSON.stringify({ freelancer_display_name: nameDraft ?? savedName }) })
      await settings.reload()
      setNameDraft(null)
      setNameFeedback(result.settings.freelancer_display_name ? 'Display name saved. New messages use this name; existing drafts are unchanged.' : 'Display name cleared. Add a name before generating a message.')
    } catch (error) { setNameError(error.message) }
    finally { setSavingName(false) }
  }
  async function generate() {
    if (busy || savingName || settings.loading || settings.error || !savedName || nameDirty || message) return
    setBusy(true); setError('')
    try { const data = await post(`/requests/${item.id}/message`, { context_aware: true }); setMessage(data.message); setDraftStatus(item.status); setSource(data.source === 'gemini' ? `AI-assisted wording selection · Gemini ${data.model} · facts composed by the app` : 'Explicit test fixture · not real AI output') }
    catch (error) { setError(error.message) }
    finally { setBusy(false) }
  }
  return <section className="card ai-panel" aria-label="Explain this payment"><div className="panel-title"><span className="ai-symbol"><Icon name="ai" size={23} /></span><div><h2>Explain this payment</h2><p className="muted">Saved facts. One next step. An AI-assisted draft.</p></div></div>
      {guidance && <div className={`payment-explanation ${item.status === 'paid' ? 'confirmed' : 'attention'}`}><h3><Icon name={item.status === 'paid' ? 'paid' : 'pending'} size={17} />What’s happening</h3><p>{guidance.explanation}</p><h3>Recommended next action</h3><p>{guidance.next_action}</p><small>Facts calculated by the app · Africa/Nairobi (UTC+3)</small></div>}
      <h3>Suggested message</h3>
      <p>{item.status === 'paid' ? 'Draft a thank-you, not another payment reminder.' : 'Draft a polite message from the saved details.'} Gemini chooses an approved wording style; the app adds payment facts. Nothing is sent automatically.</p>
      <p className="muted"><strong>Greeting recipient (client):</strong> {item.client_name?.trim() || 'No client name saved — uses “Hello,”.'}</p>
      {settings.error && <ErrorNotice message={settings.error} retry={settings.reload} />}
      {settings.loading && !settings.data && <p role="status">Loading your display name…</p>}
      {settings.data && <>
        {!savedName && <div className="notice info" role="status">Add your freelancer display name below to generate a signed message.</div>}
        <form className="display-name-form" onSubmit={saveName} aria-label="Freelancer display-name setting">
          <div className="field"><label htmlFor="freelancer-display-name">Freelancer display name</label><input id="freelancer-display-name" value={nameDraft ?? savedName} onChange={(event) => { setNameDraft(event.target.value); setNameFeedback(''); setNameError('') }} maxLength={120} disabled={savingName || busy} autoComplete="off" aria-describedby="display-name-help" placeholder="The name you want to sign with" /><small id="display-name-help">Sender name saved for this workspace in SQLite. Used only for the closing, never as the client greeting.</small></div>
          <button className="button secondary" disabled={savingName || busy || !nameDirty} type="submit">{savingName ? 'Saving name…' : 'Save display name'}</button>
          {nameError && <ErrorNotice message={nameError} />}
          {nameFeedback && <p className="name-feedback" role="status">{nameFeedback}</p>}
          {nameDirty && <p className="name-feedback">Save your display name before generating a message.</p>}
        </form>
      </>}
      <button className="button ai-button" onClick={generate} disabled={busy || savingName || settings.loading || !!settings.error || !savedName || nameDirty || !!message}><Icon name="ai" size={18} />{busy ? 'Asking Gemini…' : item.status === 'paid' ? 'Generate thank-you message' : 'Generate payment message'}</button>
      {error && <ErrorNotice message={error} retry={!message && !busy && !savingName && !!savedName && !nameDirty ? generate : undefined} />}
      {staleDraft && <div className="notice attention" role="status">Payment status changed since this draft was written. Clear it to generate current guidance, or edit it before copying.</div>}
      {source && <p className="ai-source">{source} · editable draft</p>}
      <div className="field"><label htmlFor="ai-message">Review and edit your message</label><textarea id="ai-message" rows={7} value={message} readOnly={busy} aria-busy={busy} onChange={(event) => { setMessage(event.target.value); setDraftStatus(item.status) }} placeholder="Your AI-assisted message will appear here. You can also write your own." /></div>
      <div className="ai-actions"><CopyButton text={staleDraft ? '' : message} label="Copy message" /><button className="text-button" disabled={busy || !message} onClick={() => { if (window.confirm('Discard this draft so you can generate another?')) { setMessage(''); setSource(''); setError(''); setDraftStatus(null) } }}>Clear draft</button></div>
      <small className="muted">Check every fact before sharing. Edits stay in this tab only. Copy the payment link separately.</small>
  </section>
}

function ActivityTimeline({ events = [] }) {
  return <section className="card detail-card activity-panel" aria-label="Payment activity"><h2>Payment activity</h2><p className="muted">Recorded events only · Africa/Nairobi (UTC+3). Attempt activity does not change the request’s payment status.</p><ol className="activity-list">{events.map((event, index) => <li className={`activity-event ${event.kind}`} key={`${event.kind}-${index}`}><span className="activity-icon"><Icon name={event.kind === 'payment_confirmed' ? 'paid' : event.kind === 'attempt_failed' ? 'overdue' : 'pending'} size={17} /></span><div><strong>{event.label}</strong><time dateTime={event.occurred_at}>{paymentTime(event.occurred_at)} EAT</time></div></li>)}</ol></section>
}

function Details() {
  const { id } = useParams()
  const location = useLocation()
  const { data, error, loading, reload } = useResource(`/requests/${id}`)
  const item = data?.request
  return <>
    <Link className="back-link" to="/requests">← Payment requests</Link>
    {location.state?.created && <div className="notice success" role="status"><Icon name="paid" />Request saved. Your client payment link is ready.</div>}
    {error && <ErrorNotice message={error} retry={reload} />}
    {loading && !item ? <Loading /> : item && <>
      <PageHeading eyebrow={`PAYMENT REQUEST #${item.id}`} title={item.client_name} description="Saved details, a thoughtful message, and one simple payment link." action={<Status value={item.status} />} />
      <div className="details-grid"><div className="details-left"><section className="card detail-card"><div className="card-heading"><h2>Request summary</h2><button className="text-button" disabled={loading} onClick={reload}>{loading ? 'Refreshing…' : 'Refresh status'}</button></div><div className="detail-amount">{money(item.amount_cents)} <span>USD</span></div><dl><div><dt>Client</dt><dd>{item.client_name}</dd></div><div><dt>Service</dt><dd className="preserve-text">{item.service_description}</dd></div><div><dt>Due date</dt><dd>{dueDate(item.due_date)}<small>Africa/Nairobi (UTC+3)</small></dd></div>{item.paid_at && <div><dt>Paid on</dt><dd>{new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi' }).format(new Date(item.paid_at))} EAT</dd></div>}</dl></section>
      <section className="card detail-card"><div className="panel-title"><Icon name="link" /><h2>{item.status === 'paid' ? 'Payment confirmation link' : 'Client payment link'}</h2></div><p className="muted">{item.status === 'paid' ? 'This private link shows the recorded payment confirmation, not another checkout.' : 'Anyone with this link can view the service, amount, and due date, then pay in sandbox.'}</p><label className="sr-only" htmlFor="payment-url">Client payment URL</label><input className="url-input" id="payment-url" value={item.payment_url} readOnly onFocus={(event) => event.target.select()} /><div className="link-actions"><CopyButton text={item.payment_url} label="Copy link" /><a className="text-link" href={item.payment_url} target="_blank" rel="noreferrer">Open client page ↗</a></div><small className="muted">Sandbox only. No real money moves.</small></section><ActivityTimeline events={data.activity} /></div><AIPanel item={item} guidance={data.guidance} /></div>
    </>}
  </>
}

function ClientPayment() {
  const { token } = useParams()
  const { data, error, loading, reload } = useResource(`/public/requests/${token}`)
  const config = useResource('/public/config')
  const [paymentError, setPaymentError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [orderId, setOrderId] = useState(null)
  const item = data?.request
  const base = `/public/requests/${token}`
  async function capture(id) {
    setBusy(true); setPaymentError(''); setNotice('Verifying this payment with PayPal…')
    try { await post(`${base}/capture`, { order_id: id }); setNotice('Sandbox payment confirmed. Thank you!') }
    catch (error) { setPaymentError(error.message); setNotice('') }
    finally { setBusy(false); await reload() }
  }
  return <div className="client-page"><header className="client-header"><Brand /><span className="sandbox-label">PayPal sandbox</span></header><main className="client-main" id="main">
    <div className="client-intro"><p className="eyebrow">A SIMPLE, SECURE CHECKOUT WITH PAYPAL</p><h1>Your payment request</h1><p className="muted">Review the details below before paying.</p></div>
    {error && <ErrorNotice message={error} retry={reload} />}
    {loading && !item ? <Loading /> : item && <section className="card checkout-card"><div className="checkout-top"><span className="muted">Amount requested</span><Status value={item.status} /></div><div className="checkout-amount">{money(item.amount_cents)} <span>USD</span></div><dl><div><dt>Service</dt><dd className="preserve-text">{item.service_description}</dd></div><div><dt>Due date</dt><dd>{dueDate(item.due_date)}<small>Africa/Nairobi (UTC+3)</small></dd></div></dl>
      <div className="sandbox-banner"><strong>Test payment only</strong><span>Use a PayPal sandbox buyer account. No real money will be charged.</span></div>
      {item.status === 'paid' ? <div className="payment-success" role="status"><Icon name="paid" size={40} /><h2>Payment confirmed</h2><p>This sandbox request has been paid. You’re all set.</p></div> : <>
        {config.error && <ErrorNotice message={config.error} retry={config.reload} />}
        {config.loading && !config.data && <p role="status">Loading checkout configuration…</p>}
        {config.data && !config.data.paypal_configured && <div className="notice info">Sandbox checkout is not configured yet. Ask the freelancer to configure their PayPal sandbox seller credentials.</div>}
        {config.data?.paypal_configured && <div className="paypal-checkout" aria-label="PayPal sandbox checkout"><PayPalProvider clientId={config.data.paypal_client_id} environment="sandbox" components={['paypal-payments']} pageType="checkout"><PayPalOneTimePaymentButton disabled={busy} createOrder={async () => { setPaymentError(''); setNotice(''); try { const result = await post(`${base}/orders`); setOrderId(result.order_id); return { orderId: result.order_id } } catch (error) { setPaymentError(error.message); await reload(); throw error } }} onApprove={async (data) => { setOrderId(data.orderId); await capture(data.orderId) }} onCancel={async (data) => { setNotice('Checkout cancelled. No payment was confirmed; you can try again.'); if (data.orderId) { setOrderId(data.orderId); await post(`${base}/cancel`, { order_id: data.orderId }).catch(() => {}); await reload() } }} onError={() => setPaymentError('PayPal checkout could not finish. If you approved a payment, check its status below before trying again.')} presentationMode="auto" /></PayPalProvider></div>}
        {paymentError && <ErrorNotice message={paymentError} />}
        {notice && <p className="notice info" role="status">{notice}</p>}
        {(orderId || item.active_order_id) && <button className="button secondary full-width" disabled={busy} onClick={() => capture(orderId || item.active_order_id)}>{busy ? 'Checking with PayPal…' : 'Check payment status'}</button>}
        <p className="checkout-help">Approval is not proof of payment. This page shows paid only after our server verifies a completed PayPal capture.</p>
      </>}
    </section>}
    <p className="client-footer">Powered by Freelance Flow · Sandbox demonstration<br />Payment details are shared only through this private link.</p>
  </main></div>
}

function RoutedApp() {
  const location = useLocation()
  useEffect(() => { document.title = location.pathname.startsWith('/pay/') ? 'Sandbox payment · Freelance Flow' : 'Freelance Flow · Your payment companion'; window.scrollTo(0, 0) }, [location.pathname])
  if (location.pathname.startsWith('/pay/')) return <Routes><Route path="/pay/:token" element={<ClientPayment key={location.pathname} />} /></Routes>
  return <Shell><Routes key={location.pathname}><Route path="/" element={<Dashboard />} /><Route path="/requests" element={<Requests />} /><Route path="/requests/new" element={<NewRequest />} /><Route path="/requests/:id" element={<Details />} /><Route path="*" element={<><h1>Page not found</h1><Link to="/">Return to dashboard</Link></>} /></Routes></Shell>
}

export default function App() { return <BrowserRouter><RoutedApp /></BrowserRouter> }
