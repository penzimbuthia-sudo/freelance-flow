import { useEffect, useId, useRef } from 'react'

export default function ConfirmDialog({ title, description, cancelLabel, confirmLabel, onCancel, onConfirm, returnFocusRef, fallbackFocusRef }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  const confirmRef = useRef(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    const body = dialog.ownerDocument.body
    const previousOverflow = body.style.overflow
    const trigger = returnFocusRef.current
    const fallback = fallbackFocusRef.current
    dialog.showModal() // Top-layer dialog makes the rest of the app inert.
    body.style.overflow = 'hidden'
    cancelRef.current.focus()
    return () => {
      dialog.close()
      body.style.overflow = previousOverflow
      const target = trigger?.isConnected && !trigger.disabled ? trigger : fallback
      if (target?.isConnected) target.focus()
    }
  }, [returnFocusRef, fallbackFocusRef])

  function trapFocus(event) {
    if (event.key !== 'Tab') return
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
    if (event.target !== event.currentTarget) return
    const bounds = event.currentTarget.getBoundingClientRect()
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onCancel()
  }

  return <dialog ref={dialogRef} className="confirm-dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={(event) => { event.preventDefault(); onCancel() }} onKeyDown={trapFocus} onClick={dismissBackdrop}>
    <h2 id={titleId}>{title}</h2>
    <p id={descriptionId}>{description}</p>
    <div className="confirm-dialog-actions">
      <button ref={cancelRef} className="button secondary" type="button" onClick={onCancel}>{cancelLabel}</button>
      <button ref={confirmRef} className="button primary" type="button" onClick={onConfirm}>{confirmLabel}</button>
    </div>
  </dialog>
}
