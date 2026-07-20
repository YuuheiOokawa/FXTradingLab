import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

/**
 * Full user-journey E2E test (docs/18_E2E_TESTING.md). Runs against a live
 * backend/worker/frontend stack — see that doc for how to start them. This
 * is NOT a substitute for the backend pytest suite; it exists to catch
 * integration-only failures (wrong field name across the API boundary,
 * broken navigation, a mutation nothing renders after) that unit tests
 * structurally cannot see.
 *
 * Steps mirror the real operator workflow this app is built for:
 * Dashboard -> Markets -> Chart -> Signals -> Replay (decide) -> Simulation
 * -> Backtest -> Paper order -> close -> Trade history -> Analytics ->
 * Kill Switch (armed then disarmed, so the suite leaves the app usable).
 *
 * Tests run in one worker, in file order (see playwright.config.ts), and
 * share app state (a paper position opened in one test is closed in a
 * later one) — that's intentional, it exercises the same app instance a
 * real session would.
 */

const API_BASE = process.env.E2E_API_URL ?? "http://localhost:8000";
const IGNORED_CONSOLE_PATTERNS = [/Download the React DevTools/i];

function trackPageErrors(page: Page, sink: string[]) {
  page.on("pageerror", (err) => sink.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (IGNORED_CONSOLE_PATTERNS.some((re) => re.test(text))) return;
    sink.push(`console.error: ${text}`);
  });
  page.on("requestfailed", (req) => {
    // WebSocket upgrade requests surface here too; those are expected to
    // "fail" as a plain HTTP request since they're protocol-upgraded.
    if (req.url().includes("/ws/")) return;
    sink.push(`requestfailed: ${req.url()} (${req.failure()?.errorText ?? "unknown"})`);
  });
}

async function currentPrice(request: APIRequestContext, instrument: string) {
  const res = await request.get(`${API_BASE}/api/v1/instruments/${instrument}/price`);
  expect(res.ok(), `GET /instruments/${instrument}/price should succeed`).toBeTruthy();
  return res.json() as Promise<{ bid: number; ask: number; mid: number }>;
}

test.describe.configure({ mode: "serial" });

test.describe("FX Trading Lab — full operator workflow", () => {
  let errors: string[];

  test.beforeEach(async ({ page }) => {
    errors = [];
    trackPageErrors(page, errors);
  });

  test("Dashboard loads with live status and no console/JS errors", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator("h1")).toHaveText("ダッシュボード");
    // Watchlist price tiles come from the WS-fed query; give it a moment.
    await expect(page.getByText("USD_JPY").first()).toBeVisible({ timeout: 15_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Markets page lists watched instruments", async ({ page }) => {
    await page.goto("/markets");
    await expect(page.locator("h1")).toHaveText("マーケット");
    await expect(page.getByText("USD_JPY").first()).toBeVisible({ timeout: 15_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Chart page renders a candlestick chart for USD_JPY", async ({ page }) => {
    await page.goto("/chart?instrument=USD_JPY&granularity=M15");
    // lightweight-charts draws into a canvas; its presence is the signal the
    // chart actually mounted rather than throwing during data transform.
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Signals page shows a live signal score breakdown", async ({ page }) => {
    await page.goto("/signals");
    await expect(page.locator("h1")).toHaveText("シグナル");
    await expect(page.getByText(/スコア|Score/i).first()).toBeVisible({ timeout: 15_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Replay: create a session, decide BUY with SL/TP, see a judgment, step, and close", async ({ page }) => {
    await page.goto("/replay");
    await expect(page.locator("h1")).toHaveText("リプレイ");

    await page.getByRole("button", { name: "リプレイ開始" }).click();
    await expect(page.getByText(/本目/)).toBeVisible({ timeout: 15_000 });

    await page.locator("#replay-sl-pips").fill("20");
    await page.locator("#replay-tp-pips").fill("40");
    await page.getByRole("button", { name: "BUY", exact: true }).click();

    // A decision row with a judgment badge (良い判断/普通/危険な判断) should
    // appear — the core "no future data, process-based scoring" feature.
    await expect(page.getByText(/良い判断|普通|危険な判断/).first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "次のローソク足" }).click();
    await expect(page.getByText(/本目/)).toBeVisible();

    await page.getByRole("button", { name: "決済" }).click();
    // After closing, the BUY/SELL/見送り controls reappear (no open decision).
    await expect(page.getByRole("button", { name: "見送り" })).toBeVisible({ timeout: 10_000 });

    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Simulation: submit a what-if trade and see live P/L tracking", async ({ page, request }) => {
    const price = await currentPrice(request, "USD_JPY");
    const entry = price.ask;

    await page.goto("/simulation");
    await expect(page.locator("h1")).toHaveText("シミュレーション");

    // These labels are plain sibling <label>s (not wrapping their <input>),
    // so there's no implicit a11y association for getByLabel to key off —
    // fall back to an adjacent-sibling CSS selector.
    const fieldInput = (labelText: string) => page.locator(`label:text-is("${labelText}") + input`);
    await fieldInput("エントリー価格").fill(entry.toFixed(3));
    await fieldInput("損切り (SL)").fill((entry - 0.3).toFixed(3));
    await fieldInput("利確 (TP)").fill((entry + 0.6).toFixed(3));
    await page.getByRole("button", { name: "シミュレーション開始" }).click();

    await expect(page.getByText(/含み損益|評価損益|MFE|MAE/).first()).toBeVisible({ timeout: 15_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Backtest: run a small backtest and see summary + equity curve", async ({ page }) => {
    await page.goto("/backtest");
    await expect(page.locator("h1")).toHaveText("バックテスト");

    // Small candle count so this stays fast; defaults otherwise (spread,
    // slippage, SL/TP pips) are realistic and left as-is.
    await page.getByLabel("ローソク足本数").fill("400");
    await page.getByRole("button", { name: "バックテスト実行" }).click();

    await expect(page.getByText("エクイティカーブ")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "結果" })).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Paper Trading: place a market order with SL/TP and see the position open", async ({ page, request }) => {
    const price = await currentPrice(request, "USD_JPY");

    await page.goto("/paper-trading");
    await expect(page.locator("h1")).toHaveText("Paper Trading");

    await page.getByRole("button", { name: /^BUY/ }).click();
    await page.getByLabel("Stop Loss (価格)").fill((price.bid - 0.3).toFixed(3));
    await page.getByLabel("Take Profit (価格)").fill((price.bid + 0.6).toFixed(3));
    await page.getByRole("button", { name: "買い注文を発注" }).click();

    await expect(page.getByText(/注文が約定しました/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("heading", { name: "保有ポジション" })).toBeVisible();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Paper Trading: close the open position, freeing it for the journal", async ({ page }) => {
    await page.goto("/paper-trading");
    await expect(page.getByRole("button", { name: "決済" }).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: "決済" }).first().click();
    // Position row disappears once closed (PositionsTable only lists open positions).
    await expect(page.getByRole("button", { name: "決済" })).toHaveCount(0, { timeout: 10_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Trades: the closed paper trade shows up in the journal", async ({ page }) => {
    await page.goto("/trades");
    await expect(page.locator("h1")).toHaveText("トレード履歴");
    await page.getByLabel("ソース").selectOption("paper");
    // Scope to the results table — "USD_JPY" also appears as a hidden
    // <option> in the pair filter <select>, which getByText would also match.
    await expect(page.locator("table").getByText("USD_JPY").first()).toBeVisible({ timeout: 10_000 });
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("Analytics loads win-rate and signal-outcome breakdowns without error", async ({ page }) => {
    await page.goto("/analytics");
    await expect(page.locator("h1")).toHaveText("分析");
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("System: dependency status renders, and the Kill Switch arms then disarms cleanly", async ({ page }) => {
    await page.goto("/system");
    await expect(page.locator("h1")).toHaveText("システム");
    await expect(page.getByText("Kill Switch（緊急停止）")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("依存コンポーネント")).toBeVisible();

    // Arm it (uncheck auto-flatten first — there should be nothing open at
    // this point, but this keeps the test from depending on that).
    const flattenCheckbox = page.locator('input[type="checkbox"]');
    if (await flattenCheckbox.isVisible().catch(() => false)) {
      await flattenCheckbox.uncheck();
    }
    await page.getByRole("button", { name: "Kill Switchを有効化" }).click();
    await page.getByRole("button", { name: "はい、停止する" }).click();
    await expect(page.getByText("現在の状態: 有効 (取引停止中)")).toBeVisible({ timeout: 10_000 });

    // Disarm — the suite must not leave the app in a stopped state.
    await page.getByRole("button", { name: "Kill Switchを解除" }).click();
    await expect(page.getByText("現在の状態: 無効 (通常稼働)")).toBeVisible({ timeout: 10_000 });

    expect(errors, errors.join("\n")).toEqual([]);
  });
});
