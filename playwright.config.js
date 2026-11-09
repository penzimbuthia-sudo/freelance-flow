import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './browser-tests',
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  use: { baseURL: 'http://localhost:5001', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: '.venv/bin/python -m flask --app backend:create_app run --host 127.0.0.1 --port 5001 --no-debugger --no-reload',
    url: 'http://localhost:5001/api/health',
    reuseExistingServer: false,
    env: {
      DATABASE_PATH: 'test-results/browser.sqlite3', PUBLIC_BASE_URL: 'http://localhost:5001',
      GOOGLE_API_KEY: '', GEMINI_API_KEY: '', PAYPAL_CLIENT_ID: '', PAYPAL_CLIENT_SECRET: '', PAYPAL_MERCHANT_ID: '',
      APP_HOSTS: 'localhost,127.0.0.1', FLASK_DEBUG: '0',
    },
  },
})
