import { test, expect } from '@playwright/test'

test.describe('Postflop range generation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/study')
    await page.waitForSelector('button:has-text("AA")', { timeout: 15000 })
  })

  test('sidebar contains board card picker and deal flop button', async ({ page }) => {
    const sidebar = page.locator('[data-testid="study-sidebar"]')
    await expect(sidebar).toBeVisible()

    const boardSelector = page.locator('[data-testid="board-selector"]')
    await expect(boardSelector).toBeVisible()

    const dealFlop = page.locator('[data-testid="btn-deal-flop"]')
    await expect(dealFlop).toBeVisible()
  })

  test('dealing flop updates board and shows Flop label', async ({ page }) => {
    // Click Deal Flop
    await page.locator('[data-testid="btn-deal-flop"]').click()

    // Wait for board cards to appear
    await page.waitForSelector('[data-testid="board-card-0"]', { timeout: 10000 })

    // 3 board cards visible
    await expect(page.locator('[data-testid^="board-card-"]')).toHaveCount(3)

    // Flop label appears in board selector (use board selector context)
    const boardArea = page.locator('[data-testid="board-selector"]')
    await expect(boardArea.getByText('Flop', { exact: true })).toBeVisible()
  })

  test('postflop mode fetches range and colors the matrix', async ({ page }) => {
    await page.locator('[data-testid="btn-deal-flop"]').click()
    await page.waitForSelector('[data-testid="board-card-0"]', { timeout: 10000 })

    // After postflop loads, at least some cells should have colored backgrounds
    await expect.poll(async () => {
      const cells = page.locator('[data-testid^="hand-cell-"]')
      const count = await cells.count()
      let colored = 0
      for (let i = 0; i < Math.min(count, 26); i++) {
        const cell = cells.nth(i)
        const bg = await cell.evaluate(el => el.style.background)
        if (bg && bg !== '#2a2e32' && bg !== 'rgb(42, 46, 50)') colored++
      }
      return colored
    }, { timeout: 15000 }).toBeGreaterThan(0)
  })

  test('board picker allows card selection', async ({ page }) => {
    await page.locator('[data-testid="btn-toggle-board-picker"]').click()

    const picker = page.locator('[data-testid="board-card-picker"]')
    await expect(picker).toBeVisible()

    const cardOptions = page.locator('[data-testid^="board-card-option-"]')
    expect(await cardOptions.count()).toBeGreaterThan(0)

    await cardOptions.first().click()

    // Board card added
    await page.waitForSelector('[data-testid="board-card-0"]', { timeout: 5000 })
  })
})
