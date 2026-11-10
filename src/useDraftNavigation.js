import { useCallback, useEffect } from 'react'
import { useBlocker } from 'react-router-dom'

export default function useDraftNavigation(dirty) {
  const shouldBlock = useCallback(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname, [dirty])
  const blocker = useBlocker(shouldBlock)
  useEffect(() => {
    if (!dirty) return
    function warnBeforeUnload(event) {
      // Tab close/refresh cannot reliably use an app dialog. The browser owns
      // this generic warning and may suppress it without prior user interaction.
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [dirty])
  return blocker
}
