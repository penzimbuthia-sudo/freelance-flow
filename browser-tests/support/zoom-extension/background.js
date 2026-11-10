// Test-only extension: Playwright uses tabs.setZoom for genuine browser zoom,
// not CSS zoom, a high-DPI viewport, or mobile pinch emulation.
globalThis.chrome.runtime.onInstalled.addListener(() => {})
