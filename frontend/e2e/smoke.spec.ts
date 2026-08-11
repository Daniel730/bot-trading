import { expect, test } from '@playwright/test'
import { installDashboardMocks } from './fixtures/mockApi'

test.describe('operations console smoke (mocked API, paper-safe)', () => {
  test.beforeEach(async ({ page }) => {
    await installDashboardMocks(page)
  })

  test('login screen supports token + OTP fields', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('login-screen')).toBeVisible()
    await page.getByRole('button', { name: /Use OTP instead/i }).click()
    await expect(page.getByTestId('login-token')).toBeVisible()
    await expect(page.getByTestId('login-otp')).toBeVisible()
    await expect(page.getByTestId('login-submit')).toBeVisible()
  })

  test('login with mocked OTP reaches shell; pairs hash loads panel', async ({ page }) => {
    test.setTimeout(60_000)
    await page.goto('/')
    await page.getByRole('button', { name: /Use OTP instead/i }).click()
    await page.getByTestId('login-token').fill('e2e-dashboard-token')
    await page.getByTestId('login-otp').fill('123456')
    await page.getByTestId('login-submit').click()

    await expect(page.getByTestId('dashboard-shell')).toBeVisible({ timeout: 20_000 })

    await page.evaluate(() => {
      window.location.hash = '#/pairs'
    })
    await expect(page.getByRole('heading', { name: 'Pairs' })).toBeVisible({ timeout: 20_000 })
  })
})
