# Step-driven MultiBrainEngine

SillyTavernとOpenAI互換LLMの間で動作する、6エージェント構成のロールプレイ用プロキシです。

## 処理の流れ

1. Somatic — 身体反応を評価
2. Neuro / Schema — 欲求、感情、心理スキーマを分析
3. Theory of Mind — ユーザーの意図や含みを分析
4. Default Mode Network — 空想、雑念、当日の予定を生成
5. Executive / Director — 発言と行動を決定
6. Writer — Directorの指示から最終的な文章を生成

Agents 2–4は、Agent 1の身体状態を受け取って並列に動作します。Writerには内部分析を直接渡さず、Directorが決めた発言・演技・動作だけを渡します。

## 記憶について

この版に永続的な記憶機能はありません。SQLiteの日記、人生の要約、信念ページ、シーンノート、Chronicler、Archivistは削除されています。

SillyTavernの会話履歴に含まれる直近3件の短い思考スナップショットだけを、短期的な感情の連続性に使用します。サーバーは独自のキャラクター記憶を保存しません。

## 起動

Windowsでは `start_brainengine.bat` を実行します。既存の `.venv` 内のPythonでサーバーを起動し、Gradioコントロール画面をブラウザで開きます。

```text
http://127.0.0.1:8001/ui/
```

コントロール画面にはDashboard、Providers、Prompt Studio、Lorebooks、PromptAssistantがあります。表示言語はブラウザの使用言語から日本語／英語を自動選択します。プロンプト、タイトル、ロアブック本文、チャット履歴など、ユーザーが入力した内容は表示言語を切り替えても翻訳・変更されません。

SillyTavernではCustom（OpenAI-compatible）のBase URLを次に設定します。

```text
http://127.0.0.1:8001/v1
```

Advanced FormattingのReasoningで「Add to prompt」を有効にすると、直近の思考スナップショットを次のターンへ引き継げます。

## モデル構成

- Main provider: Agents 5–6
- Logic provider（任意）: Agents 1–4

Logic providerを設定しない場合は、全エージェントがMain providerを使用します。

## ファイル

```text
engine/
  start_web_ui.py      Gradio画面とサーバー起動
  web_ui.py            Gradioコントロール画面
  launcher.py          旧Tkinter画面（移行時の互換用）
  server.py            6エージェントとOpenAI互換API
  config.json          ローカル設定（自動生成）
  config.example.json  設定例
  requirements.txt     Python依存パッケージ
```

APIキーは `engine/config.json` にのみ保存されます。

## SillyTavern extensions

SillyTavern本体はこのリポジトリに含めません。使用する拡張機能のスナップショットだけを
[`SillyTavern-extention/extensions/`](SillyTavern-extention/extensions/) に含めています。
導入手順は[こちら](SillyTavern-extention/README.md)を参照してください。

## Prompt Studio

`Group chat prompt` はSillyTavernのグループチャットでのみ、各番号付きステップとFinal outputのプロンプト直上へ追加されます。`{{user}}` はユーザーペルソナ、`{{char}}` は今回の発言者、`{{groupchar}}` は発言者を含む非ミュートメンバー、`{{allchar}}` は発言者を含む全メンバーへ展開されます。通常の1対1チャットとSummarizationには追加されません。

Prompt Studio上部の `Debug traces` をオンにすると、次の生成から各推論エージェント、Final output、Summarizeへ実際に渡された完全なメッセージ列と回答を記録します。内容は `<prompt>...</prompt>` と `<answer>...</answer>` に分けられ、プロジェクト直下の `debug` フォルダへテキストファイルとして保存されます。ファイル名はエージェント名と秒までの生成時刻です。名前が空の場合、推論ステップは `step番号`、Final outputは `finaloutput`、Summarizeは `summarize` になります。

サーバー起動中に、次のURLから各エージェントのプロンプトを編集できます。旧 `/prompts` 画面も移行互換用として残っています。

```text
http://127.0.0.1:8001/ui/
```

思考プロンプトには `[1st step]`、`[2nd step]` のような実行番号を割り当てます。番号順に逐次実行され、それぞれの出力が次のステップへ渡されます。同じ番号を複数のプロンプトへ割り当てることはできません。

思考ステップは追加・削除できます。Writerはページ下部の `Final output` に固定され、すべての思考ステップが終わった後に一度だけ実行されます。Writerは追加・削除・番号変更できません。

各ステップの右側にある `Temperature` スライダーで、そのステップだけの出力の安定性・多様性を調整できます。Writerとサマライズにも独立したTemperatureがあります。範囲は `0.00`～`1.50`、刻み幅は `0.05` です。

各Brainの分析結果は、編集画面のステップ名から作られたタグでプログラム側が自動的に囲みます。例えばタイトルが `Step 1` の場合、後続BrainとWriterへは `<step1>...分析結果...</step1>` として渡され、`[DEEP DIVE]` 内にも同じ形式で表示されます。タグ形式を各プロンプトへ書く必要はありません。

ページ下部の `Summarization` は `[[SUMMARIZE]]` 専用です。ここで要約プロンプトとTemperatureを編集できます。通常の番号付きステップやWriterとは独立しており、要約要求のときだけ使用されます。

`Save` を押すと、プロンプトとTemperature設定が `engine/prompts.json` に保存され、次の会話ターンから反映されます。設定を保存するまでは組み込みの標準プロンプトが使用されます。

新しく保存するCSVプリセットでは、`step1`～`step23` と `writer` に加えて、各Step、Writer、サマライズ用のTemperature設定が保存されます。以前の監視列を含むCSVも読み込めますが、その列は無視されます。

同じキャラクターの発言をユーザーメッセージなしで連続生成する場合も、BrainEngineは末尾に専用の制御メッセージを追加します。このメッセージは通常のロールプレイ発言と区別された書式で、KoboldCppへ新しいassistantターンを要求するための内部命令です。

### CSVプリセットの共有

Prompt Studio上部の `Preset name` に名前を入力し、`Save preset` を押すと、プロジェクト直下の `Preset` フォルダへCSVファイルが保存されます。`Export` を押すと、同じ内容をローカルへダウンロードできます。どちらにも各ステップのタイトルが含まれます。

Prompt Studioを開くと、`Preset`フォルダ内のCSVが`Saved presets…`プルダウンへ自動的に一覧表示されます。選択したプリセットはその場で現在設定として保存され、次のチャットリクエストから有効になります。新しく保存・ImportしたCSVも一覧へ即時反映されます。

CSVは1行のプリセットで、`step1`〜`step23` と `writer` のプロンプト列に加え、`step1_title`〜`step23_title`、`writer_title`、`summarize_title` のタイトル列を持ちます。使用していないステップは空欄です。改行やカンマを含むプロンプトとタイトルもCSVの引用符で保持されます。

タイトル列を持たない以前のCSVも読み込めます。その場合、番号付きステップには `Step 1` のような既定タイトルが割り当てられます。新しく保存・ExportしたCSVでは、Prompt Studioで入力したタイトルが保存され、Importまたはプリセット選択時に復元されます。

## Agent Lorebooks

コントロールウィンドウの `Lorebooks` タブでは、SillyTavern互換のWorld Infoを作成・編集し、推論ステップまたはWriterへ個別に割り当てられます。画面上部の「エージェントへの割り当て」を開くと、Prompt Studioで現在有効なすべての推論ステップとWriterが表示されます。各エージェントの右側にある検索可能なプルダウンから使用するロアブックを選び、その下の「ロアブック設定を保存」で保存してください。現在適用中のロアブック名は各エージェント名の下に表示され、数が多い場合は自動的に折り返されます。割り当て欄とプルダウン候補は、項目が多い場合に内部スクロールできます。1エージェントには複数のロアブックを割り当てられ、プルダウンの選択順に適用されます。Summarizeにはロアブックは適用されません。

`Import ST JSON` はSillyTavernから書き出したWorld Info JSONを複製して取り込みます。取り込んだデータは `engine/lorebooks.json` へ保存され、元のSillyTavernファイルとは同期されません。Prompt StudioのCSVプリセットにも含まれません。

各エントリーは常時発動またはPrimary／Secondary Keyによる発動を選択できます。標準スキャン範囲は直近2件のユーザー／アシスタントメッセージで、全体設定またはエントリー別の深度で変更できます。BrainEngine Connector 0.4.0以降から受信したキャラクターカードとユーザーペルソナも常時検索されますが、これらはメッセージのスキャン深度には含まれず、LLMプロンプトにも追加注入されません。発動した内容は次の形で、保存済みエージェントプロンプトの後、一時オーダーの前へ追加されます。

```xml
<lorebook>
<entry_name>
Lore content
</entry_name>
</lorebook>
```

本文中の `{{user}}`、`{{char}}`、`{{groupchar}}`、`{{allchar}}` はSillyTavernの役割情報を受信したリクエストで展開されます。同じリクエストで複数エージェントが同じロアブックを使う場合、発火判定は一度だけ行われます。`Token budget / agent` は誤って大量のエントリーが発動した場合の注入量を制限します。

ほかのユーザーから受け取ったCSVは `Import` から選択できます。読込に成功すると現在のプロンプト設定として保存され、次のチャットリクエストから即時反映されます。読み込んだCSVのコピーも `Preset` フォルダへ保存されます。

## SillyTavernのサマライズ

SillyTavernの要約プロンプトの先頭へ、次の専用マーカーを追加します。

```text
[[SUMMARIZE]]
```

送信されるメッセージ配列の末尾に、このマーカーだけを含むメッセージがあると、BrainEngineは番号付き思考ステップとWriterを実行せず、Main providerへ一回だけ直接要約を依頼します。メッセージのroleは`system`と`user`のどちらにも対応し、ストリーミングON/OFFの両方で動作します。

返される要約には、BrainEngineが自動的に同じマーカーを付けます。

```text
[[SUMMARIZE]]
EVENTS: ...
RELATIONSHIP: ...
OPEN CONFLICTS: ...
```

SillyTavern側では、このマーカーを含む要約全体をプロンプトへ挿入してください。通常のロールプレイ要求で履歴内にこのマーカーが見つかると、その後ろの要約文を抽出し、古い文脈としてすべての思考ステップとWriterへ固定します。

サマリーは古い情報として扱われます。直近の実際の会話と内容が矛盾した場合は、直近会話が優先されます。古い履歴内にマーカーが残っていても、配列末尾のメッセージがマーカーだけの命令でない限り、再度サマライズは実行されません。

## Requirements

- Windows
- Python 3.10+
- SillyTavern
- OpenAI互換API

PythonパッケージはFastAPI、Uvicorn、OpenAI SDK、Gradioを使用します。

新しい仮想環境や既存環境へ依存関係を追加する場合は、プロジェクト直下で次を実行します。

```text
.venv\Scripts\python.exe -m pip install -r engine\requirements.txt
```

## License

[MIT](LICENSE)
