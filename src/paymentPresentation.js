// Presentation only: status, dates and overdue days are supplied by the backend.
export const money = (cents) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100)
export const dueDate = (value) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`))
export const paymentTime = (value) => new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi' }).format(new Date(value))

export function paymentPresentation(facts) {
  const amount = money(facts.amount_cents)
  if (facts.payment_status === 'paid') return { explanation: `${amount} is recorded as paid.`, nextStep: 'send a thank-you message.' }
  let explanation = `${amount} is unpaid. Due ${dueDate(facts.due_date)}.`
  let nextStep = 'share the payment link.'
  if (facts.timing === 'today') {
    explanation = `${amount} is unpaid. Due today, ${dueDate(facts.due_date)}.`
    nextStep = 'send a polite due-today message.'
  } else if (facts.timing === 'overdue') {
    explanation = `${amount} is unpaid. ${facts.overdue_days} calendar ${facts.overdue_days === 1 ? 'day' : 'days'} overdue (due ${dueDate(facts.due_date)}).`
    nextStep = 'send a friendly follow-up.'
  }
  if (facts.attempt_outcome === 'unconfirmed') {
    explanation += ' A payment attempt needs verification.'
    nextStep = 'check payment status before trying again.'
  } else if (facts.attempt_outcome === 'cancelled') {
    explanation += ' Checkout cancellation reported by the browser.'
    nextStep = 'retry checkout using the payment link.'
  } else if (facts.attempt_outcome === 'failed' || facts.attempt_outcome === 'unavailable') {
    explanation += facts.attempt_outcome === 'failed' ? ' The last attempt failed.' : ' The previous order is unavailable.'
    nextStep = 'retry checkout using the payment link.'
  }
  return { explanation, nextStep }
}

export function hasDraftEdits(message, generatedMessage) {
  return message.trim().length > 0 && message.trim() !== generatedMessage.trim()
}

export function generationError(error) {
  const unavailable = 'Message generation is not available yet. You can still write your own message.'
  const messages = {
    ai_not_configured: unavailable,
    ai_model_unavailable: unavailable,
    ai_rate_limited: 'Message generation is busy. Please try again shortly.',
    ai_upstream_error: 'Could not generate a message. Please try again or write your own.',
    ai_empty_response: 'No message was returned. Please try again or write your own.',
    ai_invalid_response: 'We couldn’t prepare a message. Please try again or write your own.',
  }
  return Object.hasOwn(messages, error.code) ? messages[error.code] : error.message
}
