# 16. Broker Selection Review (re-verification pass)

This document exists because a re-verification was explicitly requested: does
"GMO Coin," a company primarily known as a cryptocurrency exchange, actually
offer a real 外国為替FX (margin forex) API — or did the original research
(docs/06_BROKER_API_DESIGN.md) mistakenly treat its crypto API as an FX API?
This is a legitimate thing to double-check; getting it wrong would mean
pointing a live adapter at the wrong asset class entirely.

**Conclusion: the original conclusion was correct.** GMO Coin, Inc. genuinely
operates a separate FX business with its own API, distinct from its crypto
API. Full findings below, with official/primary sources.

## GMO Coin: two separate API products, confirmed

GMO Coin, Inc. (GMOコイン株式会社) holds two separate regulatory
registrations: a crypto-exchange registration under the Payment Services Act
(資金決済法, 関東財務局長 第00006号) **and** a Financial Instruments Business
Operator registration (金融商品取引業, 関東財務局長（金商）第3188号) — the
latter is the license that permits running leveraged FX. It launched
外国為替FX as a new product line on 2023-10-28
([プレスリリース](https://prtimes.jp/main/html/rd/p/000000647.000030257.html),
[product page](https://coin.z.com/jp/corp/product/info/fx/api/)), explicitly
framed by GMO's own PR as diversification beyond crypto: "暗号資産取引のGMOコイン：
暗号資産だけじゃない！...「外国為替FX」を開始"
([PR Times](https://prtimes.jp/main/html/rd/p/000000568.000030257.000030257.html)).

The two API products do not share a namespace:

| | Crypto API | FX API |
|---|---|---|
| Docs | `api.coin.z.com/docs/` | `api.coin.z.com/fxdocs/` |
| Request host | `api.coin.z.com` | `forex-api.coin.z.com` |
| Symbols | `BTC_JPY`, `ETH_JPY`, ... | `USD_JPY`, `EUR_JPY`, `GBP_JPY`, `EUR_USD`, ... (21 pairs as of 2026-05, [announcement](https://prtimes.jp/main/html/rd/p/000000842.000030257.html)) |

**This app's default watchlist (USD_JPY, EUR_JPY, GBP_JPY, EUR_USD) is fully
covered by the FX API's pair list.** `app/brokers/gmo_coin.py` has been
updated with an explicit warning against pointing it at the crypto host by
mistake.

**Caveat, stated plainly**: automated fetches of both `api.coin.z.com/docs`
and `api.coin.z.com/fxdocs` hit anti-bot protection during this research pass
(WebFetch and a proxied curl both got blocked) — the above is triangulated
from GMO's own press releases, the product page, and independent secondary
sources, **not a direct read of the live endpoint reference**. Before writing
a real `GmoCoinAdapter` implementation, a human must open
`api.coin.z.com/fxdocs/` in a real browser and confirm exact endpoint paths,
auth header names, and payload shapes — do not implement from this document
alone.

**Re-verified in a later pass** (explicitly re-requested — "GMOコインが本当に
外国為替FX APIとして利用可能か再検証してください"): direct fetch of
`api.coin.z.com/fxdocs/` still gets blocked by anti-bot protection, same as
before — nothing has changed there. However, search-indexed content
(Google's cache of the docs page, since search engines are allowlisted where
direct fetches aren't) surfaced meaningfully more structural detail than the
first pass had, all consistent with — and strengthening — the original
conclusion, not contradicting it:
- **Public API** (no auth): latest rate retrieval + **Kline (candle/OHLC)
  data** — confirms candle-equivalent data is available, not just a raw
  ticker.
- **Private API** (API key auth): asset balance, **orders (new / settlement /
  change / cancel)**, execution info, order info, **open position lists**.
- **WebSocket**: both Public (rates) and Private (execution/order/position
  notifications) channels exist.
- English docs mirror exists at `api.coin.z.com/fxdocs/en/` (also
  anti-bot-blocked for direct fetch, same as the Japanese version).
- A 30-day free API trial and official sample code in 10 languages
  (including Python) are offered — lowers the bar for the eventual real
  implementation.

This does not change the recommendation or any conclusion above — it's
additional corroboration from the same underlying source, gathered a
different way since the direct-fetch block persists. The human-must-verify-
in-a-real-browser caveat above still stands before writing real order-path
code.

## Why not GMO Click Securities (GMOクリック証券)?

A different company in the same GMO Financial Holdings group runs the FXネオ
product. It briefly offered a Web Service API for FX **2007–2009**
([press release](https://www.click-sec.com/corp/news/press/20071031-01/)),
terminated 2009-02-14. It offers no public retail trading API today (only
proprietary desktop/mobile apps — [click-sec.com/corp/tool/](https://www.click-sec.com/corp/tool/)).
Not a viable candidate. This is a useful cautionary example of the exact
mix-up this review was checking for: "GMO" + "FX" + "API" superficially
matches three different services (GMO Coin's FX API, GMO Click's defunct API,
GMO Coin's unrelated crypto API) that must not be conflated.

## OANDA Japan — re-confirmed unchanged from docs/06

Still real, still active, still gated: REST API access requires **Gold
membership** (≈$500,000/month trading volume to maintain, though new accounts
get temporary Gold status) plus **≥¥250,000 balance on the NY server
Professional course**
([developer.oanda.com/docs/jp](https://developer.oanda.com/docs/jp/),
[API発行条件](https://www.oanda.jp/lab-education/api/usage/rest_api_activation_procedure/)).
This is why `OandaAdapter` remains the *reference/development* implementation
(its global-entity practice-account API shape is trivial to develop against)
rather than the *live* implementation target.

## Other candidates checked

- **IG証券** — has a FIX API, but per IG's own help page it is **not offered
  to individual retail customers**, platform-only
  ([IG API help](https://www.ig.com/jp/help-and-support/platforms/general-queries/how-can-i-acces-the-ig-api-and-what-can-i-use-it-for)).
  Not viable.
- **Interactive Brokers Securities Japan** — offers the IBKR Trading API to
  individual account holders, and it covers FX among other instruments
  ([interactivebrokers.co.jp/jp/trading/ib-api.php](https://www.interactivebrokers.co.jp/jp/trading/ib-api.php)).
  A legitimate secondary candidate: broader-scope brokerage (not FX-specialist),
  API is more complex (TWS/Gateway-based, not simple REST), but real and
  individually accessible. Worth a future `IbkrAdapter` if GMO Coin's account
  approval or API specifics turn out to be a blocker.
- SBI FXトレード, 楽天FX, DMM FX, 外為どっとコム — no public individual trading
  API found (consistent with docs/06's original finding); not re-litigated
  further since nothing changed here.

## Decision (unchanged from docs/06, now with higher confidence)

- **Reference/development adapter**: `OandaAdapter` (implemented) — stable,
  well-documented API shape, practice accounts trivial to obtain for
  development even though a JP resident's live account specifically requires
  the gated oanda.jp path.
- **Recommended real LIVE path for a JP resident**: GMO Coin FX API via
  `GmoCoinAdapter` (stub only — needs a funded account + a direct docs read to
  implement for real).
- **Documented fallback candidate**: Interactive Brokers Securities Japan, if
  GMO Coin doesn't pan out.
- **Always-available default**: `MockAdapter` — zero credentials, the whole
  app works without any of the above.

No changes to `BrokerAdapter`'s interface or to `06_BROKER_API_DESIGN.md`'s
core conclusion were needed as a result of this review — see
`app/brokers/gmo_coin.py`'s updated docstring for the precision fix (correct
host distinction) that *was* made.
