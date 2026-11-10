import { useEffect, useId, useRef } from 'react'

const scrollLocks = new WeakMap()

function lockScroll(body) {
  const lock = scrollLocks.get(body) || { count: 0, overflow: body.style.overflow }
  lock.count++
  scrollLocks.set(body, lock)
  body.style.overflow = 'hidden'
  return () => {
    if (--lock.count === 0) { body.style.overflow = lock.overflow; scrollLocks.delete(body) }
  }
}

export default function ConfirmDialog({ title, description, cancelLabel, confirmLabel, onCancel, onConfirm, returnFocusRef, fallbackFocusRef, busy = false, busyLabel = 'Saving…', error = '' }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  const confirmRef = useRef(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    const body = dialog.ownerDocument.body
    const trigger = returnFocusRef.current
    const fallback = fallbackFocusRef.current
    dialog.showModal() // Top-layer dialog makes the rest of the app inert.
    const unlock = lockScroll(body)
    cancelRef.current.focus()
    return () => {
      dialog.close()
      unlock()
      const target = trigger?.isConnected && !trigger.disabled ? trigger : fallback
      if (target?.isConnected) target.focus()
    }
  }, [returnFocusRef, fallbackFocusRef])

  useEffect(() => {
    if (busy) dialogRef.current.focus()
    else if (error) cancelRef.current.focus()
  }, [busy, error])

  function trapFocus(event) {
    if (event.key !== 'Tab') return
    if (busy) { event.preventDefault(); return }
    const active = event.currentTarget.ownerDocument.activeElement
    if (event.shiftKey && active === cancelRef.current) {
      event.preventDefault()
      confirmRef.current.focus()
    } else if (!event.shiftKey && active === confirmRef.current) {
      event.preventDefault()
      cancelRef.current.focus()
    }
  }

  function dismissBackdrop(event) {
    if (busy || event.target !== event.currentTarget) return
    const bounds = event.currentTarget.getBoundingClientRect()
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onCancel()
  }

  return <dialog ref={dialogRef} className="confirm-dialog" aria-modal="true" aria-busy={busy} aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={(event) => { event.preventDefault(); if (!busy) onCancel() }} onKeyDown={trapFocus} onClick={dismissBackdrop}>
    <h2 id={titleId}>{title}</h2>
    <p id={descriptionId}>{description}</p>
    {error && <div className="notice error dialog-error" role="alert">{error}</div>}
    {busy && <p role="status">{busyLabel}</p>}
    <div className="confirm-dialog-actions">
      <button ref={cancelRef} className="button secondary" type="button" disabled={busy} onClick={onCancel}>{cancelLabel}</button>
      <button ref={confirmRef} className="button primary" type="button" disabled={busy} onClick={onConfirm}>{busy ? busyLabel : confirmLabel}</button>
    </div>
  </dialog>
}
