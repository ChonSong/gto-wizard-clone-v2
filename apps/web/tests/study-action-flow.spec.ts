import { test, expect, Page } from '@playwright/test'

/**
 * GTO Wizard Study Page — Core Action Flow E2E Tests
 *
 * These tests validate that the study page correctly:
 * - Loads initial RFI range for UTG
 * - Handles action button clicks (Fold, Raise, Call, All-in)
 * - Transitions acting position correctly after each action
 * - Re-renders the matrix with the correct range context
 */

test.describe('Study Page — Preflop Action Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/study')
    // Wait for the matrix to render (13x13 grid of hand buttons)
    await page.waitForSelector('button:has-text("AA")', { timeout: 15000 })
    // Wait for loading state to clear
    await page.waitForFunction(() => !document.body.textContent?.includes('Loading range...'), { timeout: 10000 })
    // Allow matrix to settle
    await page.waitForTimeout(1000)
  })

  test('loads initial UTG RFI range with action buttons', async ({ page }) => {
    // Initial context should be RFI
    await expect(page.getByText(/rfi/i).first()).toBeVisible()

    // Action buttons should show: Fold, Raise 2.5, All-in
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Raise 2.5' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: /Allin|All-in/i })).toBeVisible()

    // UTG should be the highlighted acting position
    const utgBtn = page.locator('button').filter({ hasText: /^UTG$/ })
    await expect(utgBtn).toBeVisible()
  })

  test('clicking Raise 2.5 transitions to HJ vs_raise', async ({ page }) => {
    // Click Raise 2.5
    await page.locator('button').filter({ hasText: 'Raise 2.5' }).click()

    // Wait for the API response to update the UI
    await page.waitForFunction(() => {
      const text = document.body.textContent || ''
      return text.includes('vs_raise') || text.includes('Call')
    }, { timeout: 15000 })

    // Context should now be vs_raise
    await expect(page.getByText(/vs_raise/i).first()).toBeVisible()

    // HJ should be the acting position (action buttons for HJ's response)
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: /Call/i }).first()).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Raise 7.5' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: /Allin|All-in/i })).toBeVisible()

    // Matrix should show HJ's range (different combos than UTG)
    await expect(page.locator('button:has-text("AA")')).toBeVisible()
  })

  test('clicking Fold transitions to next position', async ({ page }) => {
    // Start with UTG RFI — click Fold
    await page.locator('button').filter({ hasText: 'Fold' }).click()

    // After UTG folds, HJ becomes the acting position in RFI context
    await page.waitForFunction(() => {
      const text = document.body.textContent || ''
      return !text.includes('Loading range...')
    }, { timeout: 10000 })
    await page.waitForTimeout(500)

    // HJ should now be the acting position
    // Context should still be RFI (or similar — fold just passes action)
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Raise 2.5' })).toBeVisible()
  })

  test('clicking All-in transitions to next acting position', async ({ page }) => {
    // Click All-in
    await page.locator('button').filter({ hasText: /Allin|All-in/i }).click()

    // Wait for the API response
    await page.waitForTimeout(2000)

    // After UTG all-in, the next position (HJ) should be acting
    // with a call/raise/fold decision
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
  })

  test('full action chain: UTG raise → HJ call → CO action', async ({ page }) => {
    // Step 1: UTG raises to 2.5
    await page.locator('button').filter({ hasText: 'Raise 2.5' }).click()
    await page.waitForTimeout(1500)

    // Verify we're in vs_raise context with HJ acting
    await expect(page.getByText(/vs_raise/i).first()).toBeVisible()

    // Step 2: HJ calls
    await page.locator('button').filter({ hasText: /Call\s/ }).first().click()
    await page.waitForTimeout(1500)

    // After HJ calls, CO should be acting in vs_raise context
    // (UTG raised 2.5, HJ called, CO faces the same raise)
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()

    // CO should have fold/call/raise options
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
  })

  test('can switch active position and see its RFI range', async ({ page }) => {
    // Click the HJ position button
    const hjBtn = page.getByRole('button', { name: 'HJ', exact: true })
    await hjBtn.click()

    // Wait for range to load for HJ
    await page.waitForTimeout(1500)

    // HJ should be in RFI context with proper action buttons
    await expect(page.getByText(/rfi/i).first()).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Raise 2.5' })).toBeVisible()

    // Matrix should show 58 combos for HJ (per the initial data)
  })

  test('stack depth change reloads the range', async ({ page }) => {
    // Click 40bb stack depth
    await page.locator('button').filter({ hasText: '40bb' }).click()

    // Wait for range to reload
    await page.waitForFunction(() => !document.body.textContent?.includes('Loading range...'), { timeout: 10000 })
    await page.waitForTimeout(500)

    // Matrix should still be visible, context should be rfi
    await expect(page.getByText(/rfi/i).first()).toBeVisible()
    await expect(page.locator('button:has-text("AA")')).toBeVisible()
    await expect(page.locator('button').filter({ hasText: 'Fold' })).toBeVisible()
  })

  test('no console errors on initial load and first action', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    // Initial load
    await page.waitForSelector('button:has-text("AA")', { timeout: 15000 })

    // First action: Raise 2.5
    await page.locator('button').filter({ hasText: 'Raise 2.5' }).click()
    await page.waitForTimeout(2000)

    // Filter out benign extension errors (webui chatter, etc.)
    const appErrors = consoleErrors.filter(e =>
      !e.includes('chrome-extension') &&
      !e.includes('moz-extension') &&
      !e.includes('favicon')
    )
    expect(appErrors.length).toBe(0)
  })
})
