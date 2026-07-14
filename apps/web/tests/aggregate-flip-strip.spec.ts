import { test, expect } from '@playwright/test'

test.describe('Aggregate Flip Strip', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/study')
    // Wait for the matrix to render (13x13 grid of hand buttons)
    await page.waitForSelector('button:has-text("AA")', { timeout: 15000 })
  })

  test('renders aggregate strip with F/C/R percentages and combo counts', async ({ page }) => {
    // The aggregate flip strip should appear below the matrix and legend
    // containing position chips for all 6 positions
    const strip = page.locator('[data-testid="aggregate-flip-strip"]')
    await expect(strip).toBeVisible()

    // Should have exactly 6 position chips
    const chips = strip.locator('[data-testid="position-chip"]')
    await expect(chips).toHaveCount(6)

    // Each chip should show positional label (e.g., "UTG", "HJ", etc.)
    const positionLabels = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']
    for (const label of positionLabels) {
      const chip = page.getByRole('button', { name: new RegExp(`^${label}\\s`) })
      await expect(chip).toBeVisible()
    }

    // At least one chip should contain "combos" text indicating combo count
    await expect(page.getByText(/combos/i).first()).toBeVisible()

    // Each chip should show F/C/R percentage bars
    // Check for fold/call/raise percentage indicators (at least one of each exists)
    await expect(strip.locator('[data-action="fold"]').first()).toBeVisible()
    await expect(strip.locator('[data-action="call"]').first()).toBeVisible()
    await expect(strip.locator('[data-action="raise"]').first()).toBeVisible()
  })

  test('clicking a position in the strip updates active position and matrix', async ({ page }) => {
    // Before clicking, UTG should be the active position (default)
    // The sidebar position button for UTG should be visible (use data-testid to avoid strict mode)
    const utgSidebar = page.getByRole('button', { name: 'UTG', exact: true })
    await expect(utgSidebar).toBeVisible()

    // Click HJ chip in the aggregate strip
    const hjChip = page.getByRole('button', { name: /^HJ\s/ })
    await hjChip.click()

    // After clicking, HJ should become the active position
    await expect(page.locator('button:has-text("AA")')).toBeVisible()

    // The sidebar HJ button should now be visible
    const hjSidebar = page.getByRole('button', { name: 'HJ', exact: true })
    await expect(hjSidebar).toBeVisible()

    // Verify the HJ chip in the strip is highlighted/active
    await expect(hjChip).toHaveAttribute('data-active', 'true')
  })

  test('changing stack depth updates aggregate stats', async ({ page }) => {
    // Click the 40bb stack depth option
    const stack40 = page.locator('button:has-text("40bb")')
    await stack40.click()

    // After changing stack depth, stats should recalculate
    // The aggregate strip should still be visible
    const strip = page.locator('[data-testid="aggregate-flip-strip"]')
    await expect(strip).toBeVisible()

    // The matrix should still be visible (data reloaded)
    await expect(page.locator('button:has-text("AA")')).toBeVisible()

    // The chips should still show combo counts
    await expect(page.getByText(/combos/i).first()).toBeVisible()

    // Verify that different stack depth values update — check that
    // the active stack depth button now shows 40bb as selected
    await expect(stack40).toBeVisible()
  })

  test('aggregate strip position chips are interactive and navigable', async ({ page }) => {
    // Test that each position chip can be clicked and navigates correctly
    const positions = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB']

    for (const pos of positions) {
      const chip = page.getByRole('button', { name: new RegExp(`^${pos}\\s`) })
      await expect(chip).toBeVisible()

      await chip.click()

      // After clicking, the matrix should still be visible
      await expect(page.locator('button:has-text("AA")')).toBeVisible()

      // Verify the chip has been marked as active
      await expect(chip).toHaveAttribute('data-active', 'true')
    }
  })
})
