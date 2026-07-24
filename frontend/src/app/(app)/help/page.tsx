import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * 使い方 (Help) — plain, jargon-free Japanese. Explanations stay simple, but the
 * writing uses ordinary kanji and no reading glosses: the reader can read, they
 * just may not know FX yet.
 *
 * No data fetching, no client hooks: a static page so it always loads, even
 * when the backend is down.
 */
export const metadata = { title: "使い方 | FX Trading Lab" };

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
        {n}
      </span>
      <span className="pt-0.5 text-sm leading-relaxed">{children}</span>
    </li>
  );
}

function ScreenRow({ emoji, name, what, when }: { emoji: string; name: string; what: string; when: string }) {
  return (
    <tr className="border-b border-border/60 align-top">
      <td className="whitespace-nowrap py-2 pr-3 text-sm font-medium">
        {emoji} {name}
      </td>
      <td className="py-2 pr-3 text-sm text-muted-foreground">{what}</td>
      <td className="py-2 text-sm text-muted-foreground">{when}</td>
    </tr>
  );
}

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">使い方 📖</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          このアプリで何ができるのか、どのボタンをいつ押すのかを順番に説明します。
        </p>
      </div>

      {/* 何をするアプリか */}
      <Card>
        <CardHeader>
          <CardTitle>❓ これは何のアプリ？</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed">
          <p>
            FXは、<b>違う国のお金を交換する取引</b>です。たとえば1ドル150円のときにドルを買い、
            160円になってから売ると、1ドルあたり10円の利益になります。この
            <b>値段の上がり下がりで利益を狙う</b>のがFXです。
          </p>
          <p>
            このアプリは、その練習を<b>本物のお金を使わずにできる道具</b>です。
            仮想のお金（ペーパー）で十分に練習してから、本物に進みます。
          </p>
          <div className="rounded-md bg-primary/10 p-3">
            <b>最初の約束：</b>まずは必ずペーパートレード（仮想のお金）から始めてください。
            本物のお金は、仕組みを理解して十分に練習してからです。
          </div>
        </CardContent>
      </Card>

      {/* 最初にやること */}
      <Card>
        <CardHeader>
          <CardTitle>🚀 初めての人はこの順番で</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            <Step n={1}>
              <b>Dashboard</b> を開いて、今の値段を眺めます。数字が動いていればアプリは正常に動いています。
            </Step>
            <Step n={2}>
              <b>Chart</b> で値段のグラフを見ます。今は上がっているのか下がっているのかを目で確認します。
            </Step>
            <Step n={3}>
              <b>Signals</b> を開きます。「今は買いか、売りか」の目安と、<b>そう判断した理由</b>が表示されます。
            </Step>
            <Step n={4}>
              <b>Paper Trading</b> で、<b>仮想の100万円</b>を使って実際に売買してみます。
              失敗しても本物のお金は減りません。
            </Step>
            <Step n={5}>
              <b>Trades / Analytics</b> で、勝てたかどうかを後から振り返ります。
            </Step>
          </ol>
        </CardContent>
      </Card>

      {/* 画面一覧 */}
      <Card>
        <CardHeader>
          <CardTitle>🗺️ どの画面で何をする？（早見表）</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">画面</th>
                <th className="py-2 pr-3 font-medium">何が見える？</th>
                <th className="py-2 font-medium">いつ使う？</th>
              </tr>
            </thead>
            <tbody>
              <ScreenRow emoji="🏠" name="Dashboard" what="今の値段のまとめ" when="最初に開く" />
              <ScreenRow emoji="🌍" name="Markets" what="監視中の通貨と性格診断" when="通貨を選ぶ・追加する" />
              <ScreenRow emoji="📈" name="Chart" what="値段のグラフ" when="値動きを目で見る" />
              <ScreenRow emoji="📡" name="Signals" what="買い / 売りの目安と理由" when="判断に迷ったとき" />
              <ScreenRow emoji="⏪" name="Replay" what="過去の相場の巻き戻し再生" when="練習・勉強" />
              <ScreenRow emoji="🧪" name="Simulation" what="1回だけの試し取引" when="思いつきを試す" />
              <ScreenRow emoji="🕐" name="Backtest" what="過去データで戦略を検証" when="戦略が有効か調べる" />
              <ScreenRow emoji="💰" name="Paper Trading" what="仮想100万円での売買" when="実際に売買する" />
              <ScreenRow emoji="✅" name="Trades" what="自分の取引履歴" when="後から振り返る" />
              <ScreenRow emoji="📊" name="Analytics" what="勝率・自動売買の成績" when="実力を確認する" />
              <ScreenRow emoji="⚙️" name="Settings" what="リスク設定・安全装置" when="運用ルールを決める" />
              <ScreenRow emoji="❤️" name="System" what="アプリの稼働状態" when="調子がおかしいとき" />
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* 売買のやり方 */}
      <Card>
        <CardHeader>
          <CardTitle>🖱️ 売買ボタンの押し方（Paper Trading）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed">
          <div>
            <p className="font-medium">🟢 これから上がりそう → 「買い（BUY）」</p>
            <ol className="mt-2 space-y-2">
              <Step n={1}>Paper Trading を開きます。</Step>
              <Step n={2}>通貨ペア（例：USD_JPY）を選びます。</Step>
              <Step n={3}>数量を入力します。最初は小さく（例：1000）。</Step>
              <Step n={4}>
                <b>「買い（BUY）」</b>を押すと、持っている状態になります。
              </Step>
              <Step n={5}>
                値上がりしたら<b>「決済」</b>を押して利益を確定します。
              </Step>
            </ol>
          </div>
          <div>
            <p className="font-medium">🔴 これから下がりそう → 「売り（SELL）」</p>
            <p className="mt-1 text-muted-foreground">
              手順は買いと同じで、<b>「売り（SELL）」</b>を押すだけです。値下がりで利益、値上がりで損失になります。
            </p>
          </div>
          <div className="rounded-md bg-amber-500/10 p-3">
            💡 <b>コツ：</b>売買する前に「どこまで上がったら利益を確定するか（利確）」と
            「どこまで下がったらやめるか（損切り）」を先に決めておくと、迷わずに済みます。
          </div>
        </CardContent>
      </Card>

      {/* 注意点 */}
      <Card>
        <CardHeader>
          <CardTitle>⚠️ 気をつけるポイント</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm leading-relaxed">
            <li>
              🧸 <b>まずはペーパー（仮想のお金）から。</b>本物のお金は、十分に練習してからにしてください。
            </li>
            <li>
              🛑 <b>損切りを怖がらないこと。</b>少し負けた時点でやめるのが、大きな損失を防ぐ一番の方法です。
            </li>
            <li>
              🍰 <b>一度に全額を使わないこと。</b>1回の取引で失ってよいのは資金の1〜2%までが目安です。
            </li>
            <li>
              😤 <b>熱くならないこと。</b>「取り返そう」と考えて続けると、さらに損失が増えることがほとんどです。
              一度手を止めましょう。
            </li>
            <li>
              🚨 <b>Settings のキルスイッチ</b>は緊急停止ボタンです。押すと新しい取引をすべて止められます。
            </li>
            <li>
              💵 <b>LIVE（本物のお金）は初期状態でオフ</b>です。オンにするには3つの条件を自分で解除する
              必要があり、自動売買から勝手に本物の注文が出ることはありません。
            </li>
          </ul>
        </CardContent>
      </Card>

      {/* 自動売買 */}
      <Card>
        <CardHeader>
          <CardTitle>🤖 自動売買の仕組み</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed">
          <p>
            Settings で「フルオート」にすると、アプリが自動で売買します。ただし対象は
            <b>ペーパー（仮想のお金）だけ</b>です。
          </p>
          <p>
            重要なのは、<b>通貨ごとに違う戦略を使っている</b>点です。すべて同じ戦略にすると負けることが、
            20年以上の実データ検証で分かっています。
          </p>
          <ul className="space-y-1">
            <li>💵 <b>USD/JPY</b>：直近20日の高値・安値を抜けたら、その方向についていく（順張り）</li>
            <li>💶 <b>EUR/JPY</b>：長期トレンドと同じ方向のときだけついていく（順張り）</li>
            <li>💷 <b>GBP/JPY</b>：下がりすぎたら買い、平均値まで戻ったら決済する（逆張り）</li>
            <li>🚫 <b>EUR/USD</b>：優位性が確認できないため停止中</li>
          </ul>
          <p>
            さらに<b>ADX</b>という指標で「今トレンドがあるか」を判定し、戦略に合わない相場では取引を見送ります。
            1回あたりの取引量も、損切りになったときの損失額が毎回同じ割合になるよう自動計算されます
            （Settings の「1トレードの最大リスク」）。
          </p>
          <div className="rounded-md bg-amber-500/10 p-3">
            ⚠️ 自動でも<b>必ず勝てるわけではありません。</b>過去20年以上の検証でも、何年も利益が出ない
            期間がありました。必ずペーパーで試してから判断してください。
          </div>
        </CardContent>
      </Card>

      {/* シグナルの見方 */}
      <Card>
        <CardHeader>
          <CardTitle>🚦 シグナルの色の意味</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm leading-relaxed">
          <p>Signals の画面では、信号機のように色で表示されます。</p>
          <ul className="space-y-1">
            <li>🟢 <b>買い / 強い買い</b>：これから上がる可能性が高いとアプリが判断した状態</li>
            <li>⚪ <b>様子見</b>：どちらとも言えない状態。無理に動かないのが正解です</li>
            <li>🔴 <b>売り / 強い売り</b>：これから下がる可能性が高いとアプリが判断した状態</li>
          </ul>
          <div className="rounded-md bg-muted p-3">
            ⚠️ シグナルは<b>必ず当たる予言ではありません。</b>あくまで判断材料の一つなので、
            外れた場合に備えて損切りを決めておいてください。
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
