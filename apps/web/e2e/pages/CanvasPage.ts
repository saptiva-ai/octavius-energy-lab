import type { Locator, Page } from "@playwright/test";
import { expect } from "@playwright/test";

export class CanvasPage {
  readonly page: Page;
  readonly canvasPanel: Locator;
  readonly plotContainer: Locator;
  readonly chartSkeleton: Locator;
  readonly plotlyChart: Locator;
  readonly closeButton: Locator;
  readonly dataTabButton: Locator;
  readonly dataRows: Locator;

  constructor(page: Page) {
    this.page = page;
    this.canvasPanel = page.locator(
      '[data-testid="canvas-panel"], [data-canvas-panel], [class*="canvas-panel"], [class*="CanvasPanel"], [data-canvas]',
    );
    this.plotContainer = this.canvasPanel.getByTestId("bank-chart-plot");
    this.chartSkeleton = this.canvasPanel.getByTestId("bank-chart-skeleton");
    this.plotlyChart = this.plotContainer.locator(
      "div.js-plotly-plot, svg.main-svg",
    );
    this.closeButton = page.getByRole("button", { name: /Cerrar|Close/i });
    this.dataTabButton = this.canvasPanel.getByRole("button", {
      name: /^Datos$/i,
    });
    this.dataRows = this.canvasPanel.locator("tbody tr");
  }

  async waitForChart(timeout = 15_000): Promise<void> {
    await expect(this.plotlyChart.first()).toBeVisible({ timeout });
  }

  async waitForChartRendered(timeout = 30_000): Promise<void> {
    await expect(this.plotContainer).toBeVisible({ timeout });
    await expect(this.plotContainer).toHaveAttribute(
      "data-chart-ready",
      "true",
      {
        timeout,
      },
    );
    await expect(this.chartSkeleton).toHaveCount(0, { timeout });
    await this.waitForChart(timeout);
  }

  async isChartVisible(): Promise<boolean> {
    return this.plotlyChart.first().isVisible();
  }

  async closeCanvas(): Promise<void> {
    await this.closeButton.click();
  }

  async waitForPanel(timeout = 10_000): Promise<void> {
    await expect(this.canvasPanel.first()).toBeVisible({ timeout });
  }

  async waitForChartSelection(timeout = 15_000): Promise<void> {
    await expect(
      this.canvasPanel.getByText("Selecciona un artefacto desde el chat."),
    ).toBeHidden({ timeout });
    await expect(this.dataTabButton).toBeVisible({ timeout });
  }

  async openDataTab(timeout = 15_000): Promise<void> {
    await this.waitForChartSelection(timeout);
    await this.dataTabButton.click();
    await expect(
      this.canvasPanel.getByRole("columnheader", { name: /Periodo/i }),
    ).toBeVisible();
  }

  async expectDataRow(params: {
    bankName: string;
    period: string;
    valuePattern?: RegExp | string;
  }): Promise<void> {
    const row = this.dataRows
      .filter({ hasText: params.bankName })
      .filter({ hasText: params.period })
      .first();

    await expect(row).toBeVisible();

    if (params.valuePattern instanceof RegExp) {
      await expect(row).toContainText(params.valuePattern);
    } else if (params.valuePattern) {
      await expect(row).toContainText(params.valuePattern);
    }
  }

  async getDataRows(
    limit = 25,
  ): Promise<
    Array<{ bank: string; period: string; value: string; raw: string[] }>
  > {
    const totalRows = await this.dataRows.count();
    const rowsToRead = Math.min(totalRows, limit);
    const rows: Array<{
      bank: string;
      period: string;
      value: string;
      raw: string[];
    }> = [];

    for (let index = 0; index < rowsToRead; index += 1) {
      const row = this.dataRows.nth(index);
      const cellTexts = (await row.locator("td").allTextContents()).map(
        (text) => text.trim(),
      );

      rows.push({
        bank: cellTexts[0] ?? "",
        period: cellTexts[1] ?? "",
        value: cellTexts[2] ?? "",
        raw: cellTexts,
      });
    }

    return rows;
  }
}
